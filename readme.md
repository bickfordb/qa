# qa

qa is simple testing library for Python.

## Features

   * Simple to use.  All tests are just functions decorated with `@qa.testcase`.  There's no gnarly class hierarchy to worry about.

        import qa

        @qa.testcase()
        def something_should_happen(context):
            if not something:
                raise Exception

   * Run tests concurrently without changing test code.
     * Run tests with 20 process workers:

            python -m qa -m myproject.tests -c process -w 20

     * Run tests with 5 thread workers:

            python -m qa -m myproject.tests -c thread -w 5

   * Unlike *unittest* you can name your testcase functions whatever you like.
   * There is no slow automatic-module-import-test-finding mechanism.  Import your test case modules once somewhere using standard Python import and your tests will get registered globally.
   * Plugin interface to customize the behavior of test runs

        class SomePlugin(qa.Plugin):
            def did_run_test_case(self, test_case, test_result):
                print test_case, "just ran with", test_result

        qa.register_plugin(SomePlugin())

   * Easily disable tests

        @qa.testcase()
        def obnoxious_test(context):
            sleep(5000)

        obnoxious_test.skip = True

   * Easily add and compose setup and teardown prerequisites

        @contextlib.contextmanager
        def world(context):
            context.world = World()
            yield
            del context.world

        @qa.testcase(requires=[world])
        def expect_something(context):
            qa.expect(context.world)

## Basic Usage

Each project should probably have a test runner module which imports all of the test modules which need to run and executes `qa.main()` when the module is invoked as the main module.

*runtests.py*

    #!/usr/bin/env python
    import qa

    import tests.mylibrary.a
    import tests.mylibrary.b

    if __name__ == '__main__':
        # Run a and b tests
        qa.main()

Here's an example test case module.  Test cases are built by writing functions and adding the `@qa.testcase()` decorator 

*tests/mylibrary/addition.py*

    import qa

    import mylibrary

    @qa.testcase()
    def test_eq(context):
        qa.expect_eq(mylibrary.two_plus_two(), 4)
 
### Disabling tests

    @qa.testcase()
    def obnoxious_test(context):
        sleep(forever)

    obnoxious_test.disabled = True
    obnoxious_test.disabled_reason = "This test takes too long!"

### Test prerequisites (aka setup/teardown)

Tests often have prequisites that need to be fulfilled before they run.  These prerequisites usually come in the form of setting up and tearing down data or resources that the test depends on.  To add a requirement to a test like this, invoke the testcase decorator like `@qa.testcase(requires=[feature1, feature2, ...])`.  Each requirement function is a context manager which is nested around the test.  The requirement function is called with a `context` object argument that can be used to exchange data with the test function.  Multiple requirement functions can be supplied and they will be nested around the test run in the order listed. 

Here's an example of using the `qa.testcase` `requires` parameter:

    @contextlib.contextmanager
    def setup_user(context):
        context.user = create_user()
        yield
        delete_user(context.user)

    @contextlib.contextmanager
    def login_user(context):
        context.user.login()
        yield
        context.user.logout()

    @qa.testcase(requires=[setup_user, login_user])
    def can_change_user_names(context):
        context.user.name = 'New Name'
        qa.expect(context.user.save())

        with qa.expect_raises(UserNameError):
            context.user.name = 'Bad User Name'
            context.user.save()

### Comparison to unittest

Using the builtin `unittest` module, you might write tests like the following:

    import unittest

    class AbstractCelestialTestCase(unittest.TestCase):
        def setUp(self):
            self.setupGalaxy()

        def tearDown(self):
            self.tearDownGalaxy()

    class MarsTestCase(AbstractCelestialTestCase):
        def setUp(self):
            super(MarsTestCase, self).setUp()
            self.mars = self.createMars()

        def testMars(self):
            self.assertEquals(self.mars.radius, expected_radius)
            self.assertEquals(self.mars.orbit, expected_orbit)
            self.assertEquals(self.mars.galaxy, self.galaxy)
 
        def tearDown(self):
            self.deleteMars(self.mars)
            super(MarsTestCase, self).tearDown()

Using the `qa` module, you write tests like the following:

    import contextlib
    import qa

    @contextlib.contextmanager
    def galaxy(context):
        galaxy = context.galaxy = Galaxy()
        yield
        del context.galaxy

    @contextlib.contextmanager
    def mars(context):
        context.mars = Mars(context.galaxy)
        yield
        del context.mars

    @qa.testcase(requires=[galaxy, mars])
    def check_mars(ctx):
        qa.expect_eq(ctx.mars.radius, expected_mars_radius)
        qa.expect_eq(ctx.mars.orbit, expected_mars_orbit)
        qa.expect_eq(ctx.galaxy, ctx.mars.galaxy)

