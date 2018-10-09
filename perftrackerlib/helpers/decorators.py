from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

# based on https://github.com/pydanny/cached-property/blob/master/cached_property.py

try:
    import asyncio
except (ImportError, SyntaxError):
    asyncio = None


class cached_property(object):
    """
    A property that is only computed once per instance and then replaces itself
    with an ordinary attribute. Deleting the attribute resets the property.
    Source: https://github.com/bottlepy/bottle/commit/fa7733e075da0d790d809aa3d2f53071897e6f76
    """  # noqa

    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self

        if asyncio and asyncio.iscoroutinefunction(self.func):
            return self._wrap_in_coroutine(obj)

        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value

    def _wrap_in_coroutine(self, obj):

        @asyncio.coroutine
        def wrapper():
            future = asyncio.ensure_future(self.func(obj))
            obj.__dict__[self.func.__name__] = future
            return future

        return wrapper()


##############################################################################
# Autotests
##############################################################################


def _coverage():
    class C:
        def __init__(self):
            self._counter = 0
            self._value = 'OK'

        @cached_property
        def value(self):
            if self._counter:
                raise Exception('Property is not cached!')
            self._counter += 1
            return self._value

    c = C()
    print(c.value)
    print(c.value)


if __name__ == "__main__":
    _coverage()
