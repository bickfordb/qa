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
def should_be_skipped(ctx):
    raise qa.Failure

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

should_be_skipped.skip = True
should_be_skipped.skip_reason = "This test always seems to fail"

