"""qa, a testing library"""

__author__ = 'Brandon Bickford <bickfordb@gmail.com>'



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
    def __init__(self, callable=None, group=None, name=None, requires=(), description=None):
        self.group = group
        self.name = name
        self.callable = callable
        self.requires = tuple(requires)
        self.description = description

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

def expect_function(function, msg, doc):
    def wrapper(*args):
        if not function(*args):
            raise Failure("expected: " + (msg % args))
    wrapper.__doc__ = doc
    return wrapper

expect_eq = expect_function(operator.eq, '%r == %r', 'expect that left is equal to right')
expect_ne = expect_function(operator.ne, '%r != %r', 'expect that left is not equal to right')
expect_gt = expect_function(operator.gt, '%r > %r', 'expect the left is greater than right')
expect_ge = expect_function(operator.ge, '%r >= %r', 'expect that left is greater than or equal to right')
expect_le = expect_function(operator.le, '%r <= %r', 'expect that left is less than or equal to right')
expect_lt = expect_function(operator.lt, '%r < %r', 'expect that left is less than right')
expect_not_none = expect_function(lambda x: x is not None, '%r is not None', 'expect is not None')
expect_not = expect_function(lambda x: x, 'not %r', 'expect evaluates False')
expect = expect_function(lambda x: x, '%r', 'expect evaluates True')

option_parser = optparse.OptionParser()
option_parser.add_option('-v', '--verbose', action='store_true')
option_parser.add_option('-f', '--filter', dest='filter', action='append')
option_parser.add_option('-m', '--mode', default='thread', choices=['single', 'process', 'thread'])
option_parser.add_option('-w', '--num-workers', default=10, type='int', help='The number of workers (if mode is "process" or "thread")')

def main(init_logging=True):
    """main method"""
    options, args = option_parser.parse_args()
    if init_logging:
        level = logging.DEBUG if options.verbose else logging.INFO
        logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    test_cases = filter_test_cases(all_test_cases, options.filter) if options.filter else all_test_cases
    run_method = {
            "thread": run_test_cases_multithread,
            "process": run_test_cases_multiprocess,
            "single": run_test_cases_singlethread,
    }[options.mode]
    run_method = run_test_cases_multithread
    test_results = run_method(test_cases, options)
    print_test_results(test_results)

def filter_test_cases(test_cases, group_and_name_filters):
    """Filter a stream of test cases according to a list of group and name filters"""
    patterns = map(re.compile, group_and_name_filters)
    for t in test_cases:
        name = t.group_and_name()
        if not patterns:
            yield t
        else:
            for p in patterns:
                if not p.search(name):
                    break
            else:
                yield t

def _run_and_queue_result(a_queue, tag, function, *args, **kwargs):
    try:
        result = function(*args, **kwargs)
        a_queue.put((tag, result))
    except Exception:
        _log.exception('An exception occurred')

def run_test_cases_multithread(test_cases, options):
    """Run test cases multithreaded"""
    max_running = options.num_workers - 1
    running = 0
    queue = Queue.Queue()
    for tag, test_case in enumerate(test_cases):
        if running == max_running:
            tag, result = queue.get()
            yield test_result
            running -= 1
        _log.debug("starting %r", test_case)
        thread.start_new_thread(_run_and_queue_result, (queue, tag, _run_test_case, test_case, options))
        running += 1 
    while running > 0:
        tag, result = queue.get()
        yield result
        running -= 1

def run_test_cases_multiprocess(test_cases, options):
    """Run test cases in a separate process for each."""
    raise NotImplementedError("multiprocess not implemented")

def mk_test_result(test_cases, failure=None, error=None, duration=None):
    return {'test_case': test_case,
            'failure': None,
            'error': None,
            'duration': None}

def _run_test_case(test_case, options):
    ctx = {}
    ctx.update(options.__dict__)
    error = None
    failure = None
    duration = None
    t0 = time.time()
    try:
        for requirement in test_case.requires:
            requirement(ctx)
        test_case.callable(ctx)
        status = 'ok'
    except Failure:
        status = 'failure'
        failure = sys.exc_info()
    except Exception:
        status = 'error'
        error = sys.exc_info()
    _log.debug('%s: %s', status, test_case.group_and_name())
    return dict(test_case=test_case, error=error, failure=failure, duration=time.time() - t0)

def run_test_cases_singlethread(test_cases, options):
    """Run a list of test cases in a single thread"""
    for test_case in test_cases:
        yield _run_test_case(test_case, options)

def print_test_results(test_results, file=None):
    if file is None:
        file = sys.stderr
    failures = 0
    errors = 0
    ok = 0
    for result in test_results:
        if result['error']:
            errors += 1
        elif result['failure']:
            failures += 1
        else:
            ok += 1
        if result['error'] or result['failure']:
           has_error = True 
           print >> file, '=' * 80
           test_case_module = result['test_case'].callable.__module__
           test_case_name = result['test_case'].callable.__name__
           failure_type = 'ERROR' if result['error'] else 'FAILURE'
           print >> file, '%s: %s' % (failure_type, result['test_case'].group_and_name())
           print >> file, '-' * 80
           for line in traceback.format_exception(*(result['error'] or result['failure']), limit=25):
               file.write(line)
           print >> file, '=' * 80
    _log.info('executed ok: %d, errors: %d, failures: %d', ok, errors, failures) 

if __name__ == '__main__': 
    main()


