"""A testing library

Intended Usage:

A "test runner" module that is responsible for running the tests for each
project.  Tests for each module or piece of functionality is often grouped
together into one test module.  

Quick example
=============

*foo.py*

    import qa

    @qa.testcase()
    def expect_something(context):
        assert 1 + 1 == 2

Run the code: python -m qa -m foo

Large Example
==============

An example project might look like the following:

 - project/ 
   - somelib/
     - module1.py
     - module2.py
   - tests/
     - module1_test.py
     - module2_test.py
   - runtests.py

-- runtests.py:
# Invoke this to run all the tests for the project
import qa
# Import the test cases:
import tests.module1_test
import tests.module2_test

if __name__ == '__main__':
    qa.main()

-- module1_test.py:

import contextlib    
import qa

@qa.testcase()
def test_module1_some_function(context):
    qa.expect_eq(some_function(a, b, c), some_result)

@contextlib.contextmanager
def setup_user(ctx):
    user = ctx['user'] = create_user()
    yield
    del ctx['user']
    delete_user(user)

@qa.testcase(requires=[setup_user]) 
def test_module1_with_a_user(ctx):
    qa.expect(ctx['user'])
"""

__author__ = 'Brandon Bickford <bickfordb@gmail.com>'
__version__ = '0.1.0'

import contextlib
import datetime
import logging
import imp
import multiprocessing
import operator
import optparse
import os
import re
import sys
import thread
import time
import traceback
import Queue

# _qa_globals: This is a separate module which stores global state.  This
# keeps global state (test case and plugin registration specifically) from
# being duplicated by multiple instances of the 'qa' module being imported.
# This can be happen when the module is imported as the main module (like via
# 'python -m qa -m sometestmodule')

try:
    import _qa_globals
except ImportError:
    _qa_globals = imp.new_module('_qa_globals')
    _qa_globals.all_test_cases = []
    _qa_globals.plugins = []
    sys.modules['_qa_globals'] = _qa_globals

_log = logging.getLogger('qa')
_test_run_log = logging.getLogger('qa.run')
_test_result_log = logging.getLogger('qa.result')
_registration_log = logging.getLogger('qa.register')

RUN_SINGLETHREAD = 'single'
RUN_MULTITHREAD = 'thread'
RUN_MULTIPROCESS = 'process'

RUN_MODES = [RUN_SINGLETHREAD, RUN_MULTITHREAD, RUN_MULTIPROCESS]

DEFAULT_NUM_WORKERS = 10

def testcase(group=None, name=None, requires=(), is_global=True):
    """Decorator for creating a test case

    Arguments
    group -- string, the group of the test.  This defaults to the module name
    name -- string, the name of the test.  This defaults to the function name
    requires -- sequence of context managers that take a dictionary paramter. Each context manager is called one at a time

    Returns
    """
    def case_decorator(function):
        name_ = function.__name__ if name is None else name
        if group is None:
            if function.__module__ != '__main__':
                group_ = function.__module__
            else:
                group_ = ''
        else:
            group_ = group
        a_test_case = TestCase(group=group_, name=name_, callable=function, requires=requires, description=function.__doc__)
        if is_global:
            register_test_case(a_test_case)
        return a_test_case
    return case_decorator

def register_test_case(test_case):
    """Globally register a test case"""
    _registration_log.debug('registering test case: %r', test_case)
    _qa_globals.all_test_cases.append(test_case)

class TestCase(object):
    """TestCase

    These are usually made with the @testcase decorator
    """
    def __init__(self, callable=None, group='', name='', requires=(), description='', skip=False, skip_reason=''):
        self.group = group
        self.name = name
        self.callable = callable
        self.requires = tuple(requires)
        self.description = description
        self.skip = skip
        self.skip_reason = skip_reason

    def group_and_name(self):
        return '%s:%s' % (self.group, self.name)

    def __repr__(self):
        return u'TestCase(group=%(group)r, name=%(name)r, callable=%(callable)r, requires=%(requires)r, description=%(description)r)' % vars(self)

    def __hash__(self):
        return hash(type(self), self.group, self.callable, self.requires, self.description)

    def __cmp__(self, other):
        return cmp((type(self), self.group, self.callable, self.requires, self.description),
                (type(other), self.group, other.callable, other.requires, other.description))

class Failure(Exception):
    """A test failure which is not a crash"""
    pass

def make_expect_function(function, msg, doc):
    """Function wrapper (decorator) for building new 'expect_' functions"""
    def wrapper(*args):
        if not function(*args):
            raise Failure("expected: " + (msg % args))
    wrapper.__doc__ = doc
    return wrapper

expect_eq = make_expect_function(operator.eq, '%r == %r', 'expect that left is equal to right')
expect_ne = make_expect_function(operator.ne, '%r != %r', 'expect that left is not equal to right')
expect_gt = make_expect_function(operator.gt, '%r > %r', 'expect the left is greater than right')
expect_ge = make_expect_function(operator.ge, '%r >= %r', 'expect that left is greater than or equal to right')
expect_le = make_expect_function(operator.le, '%r <= %r', 'expect that left is less than or equal to right')
expect_lt = make_expect_function(operator.lt, '%r < %r', 'expect that left is less than right')
expect_not_none = make_expect_function(lambda x: x is not None, '%r is not None', 'expect is not None')
expect_not = make_expect_function(lambda x: not x, 'not %r', 'expect evaluates False')
expect = make_expect_function(lambda x: x, '%r', 'expect evaluates True')
expect_contains = make_expect_function(operator.contains, '%r in %r', 'expect left is in right')
expect_isinstance = make_expect_function(isinstance, '%r isinstance %r', 'expect left is an instance of right')

def unlines(seq):
    return os.linesep.join(seq)

class TestResult(object):
    """A test result

    Construct Arguments
    group -- str, test case group name
    name -- str, test case name
    description -- str, test case description
    skipped -- bool, whether or not this test case was skipped
    skipped_reason -- str, reason the test case was skipped
    error -- exc_info tuple, an unhandled Exception that occured while the test was running
    error_msg -- str, crash message if an exc_info tuple isn't available (e.g. not pickleable)
    failure -- exc_info tuple, a Failure which occurred while the test was running
    failure_msg -- str, a failure message
    started_at -- datetime or None
    ended_at -- datetime or None

    """
    def __init__(self, group='', name='', description='', skipped=False, skipped_reason='', error=None,
            error_msg='', failure=None, failure_msg='', started_at=None, ended_at=None):
        self.group = group
        self.name = name
        self.description = description
        self.skipped = skipped
        self.skipped_reason = skipped_reason
        self.error = error
        self.error_msg = error_msg
        self.failure = failure
        self.failure_msg = failure_msg
        self.started_at = started_at
        self.ended_at = ended_at

    def __getstate__(self):

        if not self.error_msg:
            if self.error is not None:
                error_msg = ''.join(traceback.format_exception(*self.error, limit=30))
            else:
                error_msg = ''
        else:
            error_msg = self.error_msg

        if not self.failure_msg:
            if self.failure is not None:
                failure_msg = ''.join(traceback.format_exception(*self.failure, limit=30))
            else:
                failure_msg = ''
        else:
            failure_msg = self.failure_msg

        return {'group': self.group, 
                'name': self.name,
                'description': self.description,
                'skipped': self.skipped,
                'skipped_reason': self.skipped_reason,
                'error': None,
                'error_msg': error_msg,
                'failure': None,
                'failure_msg': failure_msg,
                'started_at': self.started_at,
                'ended_at': self.ended_at}

    def __setstate__(self, state):
        self.__dict__.update(state)

    @property
    def formatted_message(self):
        if self.error:
            return ''.join(traceback.format_exception(*self.error))
        elif self.error_msg:
            return self.error_msg
        elif self.failure:
            return ''.join(traceback.format_exception(*self.failure))
        else:
            return self.failure_msg

    @property
    def is_success(self):
        return (not self.skipped and
                not self.error and
                not self.error_msg and
                not self.failure and
                not self.failure_msg)

    @property
    def is_error(self):
        return bool(self.error or self.error_msg)

    @property
    def is_failure(self):
        return bool(self.failure or self.failure_msg)

    @property 
    def duration(self):
        """Get the duration time delta of the test"""
        if self.started_at is not None and self.ended_at is not None:
            return self.ended_at - self.started_at

    @property
    def status(self):
        if self.is_error:
            return u'crashed'
        elif self.is_failure:
            return u'failed'
        elif self.skipped:
            return u'skipped'
        else:
            return u'ok'

    @property
    def group_and_name(self):
        return u'%s:%s' % (self.group, self.name)

def _raises(exception_type, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
        return False
    except exception_type, exception:
        return True

expect_raises_func = make_expect_function(_raises, '%r is raised by %r', 'expect that an exception is raised')

@contextlib.contextmanager
def expect_raises(exc_type):
    """Like expect_raises_func but in contextmanager form

    Usage:

    @qa.testcase()
    def my_test(ctx):
        with expect_raises(MyException):
            two = 1 + 1
            raise MyException
        # succeeds
    """
    try:
        yield
    except exc_type, exception:
        pass
    else:
        raise qa.Failure("expected %r to be raised" % (exc_type, ))

option_parser = optparse.OptionParser()
option_parser.add_option('-v', '--verbose', action='store_true')
option_parser.add_option('-d', '--debug', action='store_true')
option_parser.add_option('-f', '--filter', dest='filter', action='append', help='Run only tests that match this regular epxression pattern.  Test names are of the form "dotted-module-path:function-name"', default=[])
option_parser.add_option('-c', '--concurrency-mode', default='single', choices=[RUN_SINGLETHREAD, RUN_MULTIPROCESS, RUN_MULTITHREAD])
option_parser.add_option('-w', '--num-workers', default=10, type='int', help='The number of workers (if mode is "process" or "thread")')
option_parser.add_option('-m', '--module', dest='modules', default=[], action='append')

def _make_name_filter(patterns):
    if patterns:
        patterns = map(re.compile, patterns)
        def filter_function(test_case):
            for p in patterns:
                if p.search(test_case.group_and_name()):
                    return True
            return False
    else:
        filter_function = lambda test_case: True
    return filter_function

def main(init_logging=True, test_cases=None, plugins=None):
    """main method"""
    options, args = option_parser.parse_args()

    if init_logging:
        level = logging.DEBUG if (options.verbose or options.debug) else logging.WARNING
        logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    _test_run_log.setLevel(logging.INFO if not options.debug else logging.DEBUG)
    _registration_log.setLevel(logging.INFO if not options.debug else logging.DEBUG)

    if test_cases is None:
        test_cases = _qa_globals.all_test_cases

    for module in options.modules:
       __import__(module) 

    name_filter = _make_name_filter(options.filter)
    test_cases = (t for t in test_cases if name_filter(t))

    if plugins is None:
        plugins = _qa_globals.plugins
    
    test_results = run_test_cases(test_cases, mode=options.concurrency_mode, num_workers=options.num_workers, plugins=plugins)
    print_test_results(test_results, plugins=plugins)

def run_test_cases(test_cases, mode=RUN_SINGLETHREAD, num_workers=None, plugins=None):
    if mode == RUN_SINGLETHREAD:
        _test_run_log.debug('executing tests in single threaded mode')
        return _run_test_cases_singlethread(test_cases, plugins=plugins)
    elif mode == RUN_MULTIPROCESS:
        _test_run_log.debug('executing tests in multiprocess mode')
        return _run_test_cases_multiprocess(test_cases, num_workers=num_workers, plugins=plugins)
    elif mode == RUN_MULTITHREAD:
        _test_run_log.debug('executing tests in multithreaded mode')
        return _run_test_cases_multithread(test_cases, num_workers=num_workers, plugins=plugins)
    else:
        raise ValueError("unexpected mode", mode)

def register_plugin(plugin):
    _registration_log.debug('adding plugin %r', plugin)
    if plugin not in _qa_globals.plugins:
        _qa_globals.append(plugin)
    else:
        _registration_log.error('plugin %r already registered', plugin)

def _run_and_queue_result(a_queue, tag, function, *args, **kwargs):
    try:
        result = function(*args, **kwargs)
        a_queue.put((tag, result))
    except Exception:
        _test_run_log.exception('An exception occurred')

def _is_skip_test_case(test_case, plugins):
    skip = test_case.skip
    skip_reason = test_case.skip_reason
    if not skip:
        if plugins is not None:
            for plugin in plugins:
                should_run = plugin.should_run_test_case(test_case)
                if should_run == True:
                    continue
                elif should_run == False:
                    skip = True
                    skip_reason = ''
                else:
                    skip = True
                    skip_reason = unicode(should_run)
                    break
    if skip:
        return TestResult(
                name=test_case.name,
                group=test_case.group, 
                description=test_case.description,
                skipped=True,
                skipped_reason=test_case.skip_reason)

def _run_test_cases_multithread(test_cases, num_workers, plugins):
    """Run test cases multithreaded"""
    if num_workers is None:
        num_workers = DEFAULT_NUM_WORKERS
    running = 0
    queue = Queue.Queue()
    for tag, test_case in enumerate(test_cases):
        skip_test_result = _is_skip_test_case(test_case, plugins)
        if skip_test_result is not None:
            yield skip_test_result
            continue
        if running >= num_workers:
            tag, result = queue.get()
            yield test_result
            running -= 1
        _test_run_log.debug("starting %r", test_case)
        thread.start_new_thread(_run_and_queue_result, (queue, tag, _run_test_case, test_case, plugins))
        running += 1 
        while running > 0:
            tag, result = queue.get()
            yield result
            running -= 1

def _run_test_cases_multiprocess(test_cases, num_workers, plugins):
    """Run test cases in a separate process for each.
    """
    if num_workers is None:
        num_workers = DEFAULT_NUM_WORKERS

    queue = multiprocessing.Queue()
    running = {}
    def run(num, test_case):
        test_result = _run_test_case(test_case, plugins)
        queue.put((num, test_result))

    for i, test_case in enumerate(test_cases):
        skip_test_result = _is_skip_test_case(test_case, plugins)
        if skip_test_result:
            yield skip_test_result
            continue
        process = multiprocessing.Process(target=run, args=(i, test_case))
        process.start()
        running[i] = process
        while len(running) >= num_workers:
            worker_num, test_result = queue.get()
            yield test_result
            running[worker_num].join()
            del running[worker_num]

    while running:
        worker_num, test_result = queue.get()
        yield test_result
        running[worker_num].join()
        del running[worker_num]
             
class Context(dict):
    def __getattr__(self, attr):
        try:
            return self.__getitem__(attr)
        except KeyError:
            raise AttributeError

    def __setattr__(self, attr, val):
        self.__setitem__(attr, val)

    def __delattr__(self, attr):
        try:
            return self.__delitem__(attr)
        except KeyError:
            raise AttributeError

def _run_test_case(test_case, plugins):
    """Helper method to run a test case.

    This is shared between the multiprocess, multithread and single thread test runners.
    """
    ctx = Context()
    error = None
    failure = None
    duration = None
    t0 = time.time()
    test_result = TestResult(group=test_case.group, name=test_case.name, description=test_case.description, started_at=datetime.datetime.now())
    try:
        requirements = []
        for plugin in plugins:
            for requirement in plugin.extra_test_case_requirements(test_case):
                requirements.append(requirement(ctx))
        requirements.extend(requirement(ctx) for requirement in test_case.requires)
        with contextlib.nested(*requirements):
            for plugin in plugins:
                plugin.will_run_test_case(test_case, ctx)
            test_case.callable(ctx)
        status = 'passed'
    except Failure:
        status = 'failed'
        test_result.failure = sys.exc_info()
    except Exception:
        status = 'crashed'
        test_result.error = sys.exc_info()
    test_result.ended_at = datetime.datetime.now()
    _test_run_log.debug('test %s: %r', test_result.status, test_result.group_and_name)
    if plugins is not None:
        for plugin in plugins:
            plugin.did_run_test_case(test_case, test_result, ctx)
    return test_result

def _run_test_cases_singlethread(test_cases, plugins):
    """Run a list of test cases in a single thread"""
    for test_case in test_cases:
        skip_test_result = _is_skip_test_case(test_case, plugins)
        if skip_test_result is not None:
            yield skip_test_result
        else:
            yield _run_test_case(test_case, plugins)

def print_test_results(test_results, plugins, file=None):
    """Print a stream of test results

    Each test error or failure will be printed to 'file'

    Arguments
    test_results -- stream of test results
    file -- None
    """
    if file is None:
        file = sys.stderr
    failures = 0
    errors = 0
    skipped = 0
    ok = 0
    for result in test_results:
        if result.is_error:
            errors += 1
        elif result.is_failure:
            failures += 1
        elif result.skipped:
            skipped += 1
        else:
            ok += 1
        if result.is_success:
            _test_result_log.info('test %r %s', result.group_and_name, result.status)
        elif result.skipped:
            _test_result_log.warning('test %r %s', result.group_and_name, result.status)
        else:
            _test_result_log.error('test %r %s:\n%s', result.group_and_name, result.status, result.formatted_message)
    _test_result_log.info('executed ok: %d, errors: %d, failures: %d, skipped: %d', ok, errors, failures, skipped) 

class Plugin(object):
    """Abstract Plugin class"""
    def should_run_test_case(self, test_case):
        """This is called before a test case is queued to be run

        Arguments
        test_case, TestCase

        Returns
        True -- the test case should be run
        False -- the test case should not be run
        """
        return True

    def will_run_test_case(self, test_case, context):
        """This is called whenever a test case is about to be run"""
        pass

    def did_run_test_case(self, test_case, test_result, context):
        """This is called whenever a test case is run with the test result dictionary"""
        pass

    def did_skip_test_case(self, test_case, test_result):
        """This is called whenever a test case is skipped with the test case and test result"""
        pass

    def will_fork(self):
        pass

    def did_fork(self):
        pass

    def will_clone(self):
        pass

    def did_clone(self):
        pass

    def extra_test_case_requirements(self, test_case):
        """This is called before test case requirements are setup to add any additional requirements

        Arguments
        test_case -- 

        Returns
        a list of context managers that take a Context argument
        """
        return []

if __name__ == '__main__': 
    main()
