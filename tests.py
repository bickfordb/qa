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

should_be_skipped.disabled = True
should_be_skipped.disabled_reason = "This test always seems to fail"

