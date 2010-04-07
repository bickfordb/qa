import contextlib
import qa

@qa.testcase()
def test_expect(ctx):
    qa.expect(True)
    with qa.expect_raises(qa.Failure):
        qa.expect(False)

@qa.testcase()
def test_expect_not(ctx):
    qa.expect_not(False)
    with qa.expect_raises(qa.Failure):
        qa.expect_not(True)

@qa.testcase()
def test_expect_not_none(ctx):
    qa.expect_not_none(False)
    qa.expect_not_none(True)
    qa.expect_not_none(object())
    qa.expect_not_none(0)
    with qa.expect_raises(qa.Failure):
        qa.expect_not_none(None)

@contextlib.contextmanager
def _setup_example(ctx):
    ctx.foo = 1
    try:
        yield
    finally:
        del ctx.foo

@qa.testcase(requires=[_setup_example])
def test_requires(ctx):
    """Make sure requires works"""
    qa.expect_eq(ctx.foo, 1)   

@qa.testcase()
def expect_raises_should_work(ctx):
    """Make sure that expect_raises() works"""
    with qa.expect_raises(KeyError):
        {}[0]

@qa.testcase()
def context_works_like_object_and_dict(ctx):
    ctx.x = 1
    qa.expect_eq(ctx['x'], 1)
    del ctx['x']
    ctx.x = 1
    del ctx.x
    ctx.x = 1
    qa.expect_eq(ctx.x, 1)
    qa.expect_eq(list(ctx), ['x'])
    qa.expect_eq(list(ctx.values()), [1])
    qa.expect_eq(list(ctx.items()), [('x', 1)])

@qa.testcase()
def skip_works(context):
    @qa.testcase(is_global=False)
    def _skip(ctx):
        pass
    _skip.skip = True
    _skip.skip_reason = 'Should be skipped'

    results = qa.run_test_cases([_skip])
    results = list(results)
    qa.expect_eq(results[0].skipped, True)
    qa.expect_eq(results[0].skipped_reason, 'Should be skipped')

