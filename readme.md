qa, Python Testing Library
--------------------------

### Usage

Each project should have a test runner module:

#### runtests.py 

    #!/usr/bin/env python
    import qa

    import tests.mylibrary.a
    import tests.mylibrary.b

    if __name__ == '__main__':
        # Run a and b tests
        qa.main()

Here's an example test case module:

#### tests/mylibrary/addition.py

    import qa

    import mylibrary

    @qa.testcase()
    def test_eq():
        qa.expect_eq(mylibrary.two_plus_two(), 4)
 
 
