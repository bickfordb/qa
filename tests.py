import contextlib
import qa

@qa.testcase()
def test_expect(ctx):
    qa.expect(True)
    qa.expect_raises(qa.Failure, qa.expect, False)

@qa.testcase()
def test_expect_not(ctx):
    qa.expect_not(False)
    qa.expect_raises(qa.Failure, qa.expect_not, True)

@qa.testcase()
def test_expect_not_none(ctx):
    qa.expect_not_none(False)
    qa.expect_not_none(True)
    qa.expect_not_none(object())
    qa.expect_not_none(0)
    qa.expect_raises(qa.Failure, qa.expect_not_none, None)

@contextlib.contextmanager
def _setup_example(ctx):
    ctx['foo'] = 1
    try:
        yield
    finally:
        del ctx['foo']

@qa.testcase(requires=[_setup_example])
def test_requires(ctx):
    """Make sure requires works"""
    qa.expect_eq(ctx['foo'], 1)   

@qa.testcase()
def test_should_fail(ctx):
    with qa.expect_raises_ctx(KeyError):
        {}[0]

