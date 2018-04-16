import time
import datetime
import calendar
"""
Various functions to help working with time, time differences and delays
"""

time_now = datetime.datetime.today

def seconds(sec):
	return datetime.timedelta(0, sec)

def seconds_between( new_time, old_time ):
	td = new_time - old_time
	return float(td.days * 3600 * 24 + td.seconds) + td.microseconds/1000000.0

def time_t_as_string(t):
	ts = time.gmtime(t)
	s = "%4d-%02d-%02d %02d:%02d:%02d" % ts[:6]
	frac = t - int(t)
	if frac >= 0.000001:
		s += ".%06d" % int(frac*1000000)
	return s

def date_only(t):
	# since timestamp 't' can come from external machine with own TZ, we have to treat it as UTC
	# and avoid any conversions based on local TZ
	return calendar.timegm(datetime.datetime.utcfromtimestamp(t).date().timetuple())

epoch = datetime.datetime(1970, 1, 1)
def datetime_utc_to_timestamp(d):
	return seconds_between(d, epoch)

def time_only(t):
	return t - date_only(t)

class SomeProgress:
	pass

def adaptive_wait(func, params=None, timeout=0, progress_timeout=0, max_delay=1.0, initial_delay=0.02):
	""" Call func( params ) repeatedly until it returns something not None and not SomeProgress.
	Returning SomeProgress or SomeProgress() helps to detect wait progress (only if progress_timeout > 0).

	Calls are interleaved with time.sleep() with increasing delay.
	Gives up at <timeout> seconds unless timeout is 0.
	Also gives up if progress_timeout > 0 and function didn't return SomeProgress within progress_timeout seconds.
	Returns tuple ( func-result, seconds-spent-in-waiting, is-timed-out )
	"""
	delay = initial_delay
	start = last_progress = time_now()
	ret = None
	spent = 0.0
	is_timeout = False
	while True:
		ret = func( params )
		now = time_now()
		spent = seconds_between( now, start )
		if ret == SomeProgress or isinstance(ret, SomeProgress):
			ret = None
			delay = initial_delay
			last_progress = now
		elif ret != None:
			break
		since_progress = seconds_between( now, last_progress )
		is_timeout = (timeout > 0 and spent >= timeout) or (progress_timeout > 0 and since_progress > progress_timeout)
		if is_timeout:
			break
		time.sleep( delay )
		delay = min( max_delay, delay * 1.5 )
	return ( ret, spent, is_timeout )


