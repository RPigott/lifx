import inspect
import sys
import msvcrt
import re
import itertools
import functools
import textwrap
from decorator import decorator

def main(fn):
	active = inspect.stack()[1][0].f_locals['__name__']=='__main__'
	interactive = sys.flags.interactive
	if active and not interactive:
		args = sys.argv[1:]
		fn(*args)
	return fn

def mainp(*parsers):
	# @decorator
	def dec(fn):
		active = inspect.stack()[1][0].f_locals['__name__']=='__main__'
		interactive = sys.flags.interactive
		if active and not interactive:
			args = [parser(arg) for parser,arg in zip(parsers,sys.argv[1:])]
			fn(*args)
		return fn
	return dec

def formatdoc(fn):
	if fn.__doc__:
		fn.__doc__ = textwrap.dedent(fn.__doc__)
		fn.__doc__ = textwrap.fill(fn.__doc__,replace_whitespace=False)
		fn.__doc__ = textwrap.indent(fn.__doc__,'\t')
	return fn

def allmethoddec(decorator):
	def clsdec(cls):
		function = type(lambda: None)
		for name in dir(cls):
			if not name.startswith('__') and isinstance(name, function):
				print(name)
				setattr(A,name,decorator(getattr(A,name)))
		return cls
	return clsdec

def take(n, it):
	c = itertools.count()
	return itertools.takewhile(lambda _: next(c) < n, it)

def cutparen(s):
	r = re.compile(r' ?\([^)(]*\)')
	while re.search(r,s):
		s = re.sub(r,'',s)
	return s

def yorn(prompt = '[y/n]: '):
	print(prompt, end='')
	sys.stdout.flush()
	c = msvcrt.getwch()
	if c is 'y' or c is '\r':
		return True
	else:
		return False

'''Numpy Stuff'''
import numpy as np
def blockshaped(arr, nrows, ncols):
	"""
	Return an array of shape (n, nrows, ncols) where
	n * nrows * ncols = arr.size

	If arr is a 2D array, the returned array should look like n subblocks with
	each subblock preserving the "physical" layout of arr.
	"""
	h, w = arr.shape
	return (arr.reshape(h//nrows, nrows, -1, ncols)
	           .swapaxes(1,2)
	           .reshape(-1, nrows, ncols))

import itertools as it
def nth(iterable, n, default=None):
    "Returns the nth item or a default value"
    return next(it.islice(iterable, n, None), default)