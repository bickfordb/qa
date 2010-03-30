"""a testing library

Intended Usage:

A "test runner" module that is responsible for running the tests for each
project.  Tests for each module or piece of functionality is often grouped
together into one test module.  

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

import contextlib
import logging
import operator
import optparse
import re
import sys
import thread
import time
import traceback
import Queue

all_test_cases = []

_log = logging.getLogger('qa')

def testcase(group=None, name=None, requires=()):
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
        o = TestCase(group=group_, name=name_, callable=function, requires=requires, description=function.__doc__)
        all_test_cases.append(o)
        return o
    return case_decorator

class TestCase(object):
    def __init__(self, callable=None, group=None, name=None, requires=(), description=None, disabled=False, disabled_reason=''):
        self.group = group
        self.name = name
        self.callable = callable
        self.requires = tuple(requires)
        self.description = description
        self.disabled = disabled
        self.disabled_reason = disabled_reason

    def group_and_name(self):
        return '%s:%s' % (self.group, self.name)

    def __repr__(self):
        return u'TestCase(group=%(group)r, callable=%(callable)r, requires=%(requires)r, description=%(description)r)' % vars(self)

    def __hash__(self):
        return hash(type(self), self.group, self.callable, self.requires, self.description)

    def __cmp__(self, other):
        return cmp((type(self), self.group, self.callable, self.requires, self.description),
                (type(other), self.group, other.callable, other.requires, other.description))

class Failure(Exception):
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
option_parser.add_option('-f', '--filter', dest='filter', action='append', help='Run only tests that match this regular epxression pattern.  Test names are of the form "dotted-module-path:function-name"', default=[])
option_parser.add_option('-m', '--concurrency-mode', default='thread', choices=['single', 'process', 'thread'])
option_parser.add_option('-w', '--num-workers', default=10, type='int', help='The number of workers (if mode is "process" or "thread")')

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

def main(init_logging=True, test_cases=None):
    """main method"""
    options, args = option_parser.parse_args()
    if init_logging:
        level = logging.DEBUG if options.verbose else logging.INFO
        logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if test_cases is None:
        test_cases = all_test_cases
    name_filter = _make_name_filter(options.filter)
    test_cases = (t for t in test_cases if name_filter(t))

    if options.concurrency_mode == "single":
        _log.debug('executing tests in single threaded mode')
        test_results = run_test_cases_singlethread(test_cases)
    elif options.concurrency_mode == "process":
        _log.debug('executing tests in multiprocess mode')
        test_results = run_test_cases_multiprocess(test_cases, num_workers=options.num_workers)
    else:
        _log.debug('executing tests in multithreaded mode')
        test_results = run_test_cases_multithread(test_cases, num_workers=options.num_workers)
    print_test_results(test_results)

def _run_and_queue_result(a_queue, tag, function, *args, **kwargs):
    try:
        result = function(*args, **kwargs)
        a_queue.put((tag, result))
    except Exception:
        _log.exception('An exception occurred')

def run_test_cases_multithread(test_cases, num_workers):
    """Run test cases multithreaded"""
    running = 0
    queue = Queue.Queue()
    for tag, test_case in enumerate(test_cases):
        if test_case.disabled:
            yield dict(test_case=test_case, skipped=True, error=None, failure=None, duration=0)
            continue
        if running >= num_workers:
            tag, result = queue.get()
            yield test_result
            running -= 1
        _log.debug("starting %r", test_case)
        thread.start_new_thread(_run_and_queue_result, (queue, tag, _run_test_case, test_case))
        running += 1 
    while running > 0:
        tag, result = queue.get()
        yield result
        running -= 1

def run_test_cases_multiprocess(test_cases, num_workers):
    """Run test cases in a separate process for each."""
    raise NotImplementedError("multiprocess not implemented")

class Context(object):
    pass

def _run_test_case(test_case):
    ctx = Context()
    error = None
    failure = None
    duration = None
    t0 = time.time()
    try:
        requirements = [requirement(ctx) for requirement in test_case.requires]
        with contextlib.nested(*requirements):
            test_case.callable(ctx)
        status = 'passed'
    except Failure:
        status = 'failed'
        failure = sys.exc_info()
    except Exception:
        status = 'crashed'
        error = sys.exc_info()
    _log.debug('test %s: %r', status, test_case.group_and_name())
    return dict(test_case=test_case, error=error, skipped=False, failure=failure, duration=time.time() - t0)

def run_test_cases_singlethread(test_cases):
    """Run a list of test cases in a single thread"""
    for test_case in test_cases:
        if test_case.disabled:
            yield dict(test_case=test_case, skipped=True, error=None, failure=None, duration=0)
        else:
            yield _run_test_case(test_case)

def print_test_results(test_results, file=None):
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
        if result['error']:
            errors += 1
        elif result['failure']:
            failures += 1
        elif result['skipped']:
            skipped += 1
        else:
            ok += 1
        if result['error'] or result['failure']:
            _log.error('test %r failed', result['test_case'].group_and_name(), exc_info=result['error'] or result['failure'])
    _log.info('executed ok: %d, errors: %d, failures: %d, skipped: %d', ok, errors, failures, skipped) 

if __name__ == '__main__': 
    main()


