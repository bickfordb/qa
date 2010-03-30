qa: Python Testing Library
--------------------------

### Basic Usage

Each project should have a test runner module which imports all of the test module which need to run and executing "qa.main()" when the module is invoked as the main module.

#### runtests.py 

    #!/usr/bin/env python
    import qa

    import tests.mylibrary.a
    import tests.mylibrary.b

    if __name__ == '__main__':
        # Run a and b tests
        qa.main()

Here's an example test case module.  Test cases are built by writing functions and adding the "@qa.testcase()" decorator 

#### tests/mylibrary/addition.py

    import qa

    import mylibrary

    @qa.testcase()
    def test_eq(context):
        qa.expect_eq(mylibrary.two_plus_two(), 4)
 
### Disabling tests

    import qa

    @qa.testcase()
    def obnoxious_test(context):
        sleep(forever)

    obnoxious_test.disabled = True
    obnoxious_test.disabled_reason = "This test takes too long!"

### Test prerequisites (aka setup/teardown)

Tests often have prequisites that need to be fulfilled before they run.  These prerequisites often come in the form of setting up and tearing down data or resources that the test depends on.  To add a requirement to a test like this, invoke the testcase decorator like "@qa.testcase(requires=[requirement1, requirement2, ...])".  Each requirement function is a context manager which is nested around the test.  The requirement function is called with a dictionary argument that can be used to exchange data with the test function.  Multiple requirement functions can be supplied and they will be nested around the test run in the order listed. 

Here's an example of using the "qa.testcase" "requires" parameter:

    import contextlib

    import qa

    @contextlib.contextmanager
    def setup_sun_should_rise(context):
        context['sun'] = True
        yield
        del context['sun']

    @qa.testcase(requires=[setup_sun_should_rise]):
    def sun_should_rise(context):
        qa.expect_eq(context['sun'], True)

    @contextlib.contextmanager
    def setup_user(context):
        context['user'] = create_user()
        yield
        delete_user(context['user'])

    @contextlib.contextmanager
    def login_user(context):
        context['user'].login()
        yield
        context['user'].logout()

    @qa.testcase(requires=[setup_user, login_user])
    def some_test_that_needs_fixture_data(context):
        qa.expect_eq(context['fixtures'])

### Comparison to unittest

Using the builtin "unittest" module, you write tests like the following:

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

Using the "qa" module, you write tests like the following:

    import contextlib
    import qa

    @contextlib.contextmanager
    def setup_galaxy(context):
        galaxy = context['galaxy'] = Galaxy()
        yield
        del context['galaxy']

    @contextlib.contextmanager
    def setup_mars(context):
        context['mars'] = Mars()
        yield
        del context['mars']

    @qa.testcase(requires=[setup_galaxy, setup_mars])
    def check_mars(ctx):
        qa.expect_eq(ctx['mars'].radius, expected_mars_radius)
        qa.expect_eq(ctx['mars'].orbit, expected_mars_orbit)
        qa.expect_eq(ctx['galaxy'], ctx['mars'].galaxy)

