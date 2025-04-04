#
# Copyright (C) 2010-2017 Samuel Abels
# The MIT License (MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
from Exscript.stdlib.util import secure_function


@secure_function
def new(scope):
    """
    Returns a new, empty list.

    :rtype:  string
    :return: The model of the remote device.
    """
    return []


@secure_function
def length(scope, mylist):
    """
    Returns the number of items in the list.

    :rtype:  string
    :return: The model of the remote device.
    """
    return [len(mylist)]


@secure_function
def get(scope, source, index):
    """
    Returns a copy of the list item with the given index.
    It is an error if an item with teh given index does not exist.

    :type  source: string
    :param source: A list of strings.
    :type  index: string
    :param index: A list of strings.
    :rtype:  string
    :return: The cleaned up list of strings.
    """
    try:
        index = int(index[0])
    except IndexError:
        raise ValueError('index variable is required')
    except ValueError:
        raise ValueError('index is not an integer')
    try:
        return [source[index]]
    except IndexError:
        raise ValueError('no such item in the list')


@secure_function
def unique(scope, source):
    """
    Returns a copy of the given list in which all duplicates are removed
    such that one of each item remains in the list.

    :type  source: string
    :param source: A list of strings.
    :rtype:  string
    :return: The cleaned up list of strings.
    """
    return dict(map(lambda a: (a, 1), source)).keys()
