/*
 * Date() but with microseconds resolution
 */

/*
 * uDate is similar to Date, but it has microsecond resolution
 *
 * Changed API:
 * - new uDate(usec)
 * - new uDate(year, month, day, hours, minutes, seconds, usec)
 *
 * New API:
 * - uDate().getMicroseconds() - return number of usecs in msec (the same semantic like getMilliseconds)
 * - uDate().setMicroseconds() - set number of usec
 */

function uDate()
{
	this._us = 0;	// number of microseconds in 1 millisecond
	var utc_adjust = true;

	switch (arguments.length) {
	case 7:
		var arg6 = Math.round(arguments[6]);
		this._us = arg6 % 1000;
		this._date = new Date(arguments[0], arguments[1], arguments[2], arguments[3],
								arguments[4], arguments[5], Math.floor(arg6 / 1000));
		break;
	case 6:
		this._date = new Date(arguments[0], arguments[1], arguments[2], arguments[3],
								arguments[4], arguments[5]);
		break;
	case 5:
		this._date = new Date(arguments[0], arguments[1], arguments[2], arguments[3], arguments[4]);
		break;
	case 3:
		this._date = new Date(arguments[0], arguments[1], arguments[2]);
		break;
	case 1:
		if (typeof arguments[0] == "number") {
			var arg = Math.round(arguments[0]);
			this._us = arg % 1000;
			this._date = new Date(Math.floor(arg/1000));
			utc_adjust = false;
		} else {
			this._date = new Date(arguments[0]);
		}
		break;
	case 0:
		this._date = new Date();
		break;
	default:
		alert("Fix uDate: constructor have " + arguments.length + " args");
	}

	/*
	if (arguments.length == 1 && isNaN(arguments[0]))
		debugger;
	*/
	if (utc_adjust)
		this._date = new Date(this._date.getTime() - this._date.getTimezoneOffset() * 60000);
}

var dateFormat = function () {
	var	token = /d{1,4}|m{1,4}|yy(?:yy)?|([HhMsTt])\1?|[LloSZIUD]|u{1,3}|"[^"]*"|'[^']*'/g,
		timezone = /\b(?:[PMCEA][SDP]T|(?:Pacific|Mountain|Central|Eastern|Atlantic) (?:Standard|Daylight|Prevailing) Time|(?:GMT|UTC)(?:[-+]\d{4})?)\b/g,
		timezoneClip = /[^-+\dA-Z]/g,
		pad = function (val, len) {
			val = String(val);
			len = len || 2;
			while (val.length < len) val = "0" + val;
			return val;
		};

	// Regexes and supporting functions are cached through closure
	return function (date, mask, utc) {
		var dF = dateFormat;

		// You can't provide utc if you skip other args (use the "UTC:" mask prefix)
		if (arguments.length == 1 && Object.prototype.toString.call(date) == "[object String]" && !/\d/.test(date)) {
			mask = date;
			date = undefined;
		}

		// Passing date through Date applies Date.parse, if necessary
		date = date ? new uDate(date.valueOf()) : new uDate;
		if (isNaN(date)) throw SyntaxError("invalid date");

		mask = String(dF.masks[mask] || mask || dF.masks["default"]);

		// Allow setting the utc argument via the mask
		if (mask.slice(0, 4) == "UTC:") {
			mask = mask.slice(4);
			utc = true;
		}

		var	_ = utc ? "getUTC" : "get",
			d = date[_ + "Date"](),
			D = date[_ + "Day"](),
			m = date[_ + "Month"](),
			y = date[_ + "FullYear"](),
			H = date[_ + "Hours"](),
			M = date[_ + "Minutes"](),
			s = date[_ + "Seconds"](),
			L = date[_ + "Milliseconds"](),
			u = date.valueOf(),
			o = utc ? 0 : date.getTimezoneOffset(),
			flags = {
				d:    d,
				dd:   pad(d),
				ddd:  dF.i18n.dayNames[D],
				dddd: dF.i18n.dayNames[D + 7],
				m:    m + 1,
				mm:   pad(m + 1),
				mmm:  dF.i18n.monthNames[m],
				mmmm: dF.i18n.monthNames[m + 12],
				yy:   String(y).slice(2),
				yyyy: y,
				h:    H % 12 || 12,
				hh:   pad(H % 12 || 12),
				H:    H,
				HH:   pad(H),
				M:    M,
				MM:   pad(M),
				s:    s,
				ss:   pad(s),
				l:    pad(L, 3),
				L:    pad(L > 99 ? Math.round(L / 10) : L),
				I:    Math.floor(u / 1000),
				u:    Math.floor((u % 1000) / 100),
				uu:   pad(Math.floor((Math.abs(u) % 1000) / 10), 2),
				uuu:  pad(Math.abs(u) % 1000, 3),
				D:    Math.floor(u / (1000000 * 60 * 60)),
				U:    u,
				t:    H < 12 ? "a"  : "p",
				tt:   H < 12 ? "am" : "pm",
				T:    H < 12 ? "A"  : "P",
				TT:   H < 12 ? "AM" : "PM",
				Z:    utc ? "UTC" : (String(date).match(timezone) || [""]).pop().replace(timezoneClip, ""),
				o:    (o > 0 ? "-" : "+") + pad(Math.floor(Math.abs(o) / 60) * 100 + Math.abs(o) % 60, 4),
				S:    ["th", "st", "nd", "rd"][d % 10 > 3 ? 0 : (d % 100 - d % 10 != 10) * d % 10]
			};

		return mask.replace(token, function ($0) {
			return $0 in flags ? flags[$0] : $0.slice(1, $0.length - 1);
		});
	};
}();

// Some common format strings
dateFormat.masks = {
	"default":      "ddd mmm dd yyyy HH:MM:ss",
	shortDate:      "m/d/yy",
	mediumDate:     "mmm d, yyyy",
	longDate:       "mmmm d, yyyy",
	fullDate:       "dddd, mmmm d, yyyy",
	shortTime:      "h:MM TT",
	mediumTime:     "h:MM:ss TT",
	msecTime:		"HH:MM:ss.L",
	msec:			"I.uu",
	usec:			"U",
	deltaHours:		"D:MM:ss",
	longTime:       "h:MM:ss TT Z",
	isoDate:        "yyyy-mm-dd",
	isoTime:        "HH:MM:ss",
	isoDateTime:    "yyyy-mm-dd'T'HH:MM:ss",
	isoUtcDateTime: "UTC:yyyy-mm-dd'T'HH:MM:ss'Z'"
};

// Internationalization strings
dateFormat.i18n = {
	dayNames: [
		"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
		"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
	],
	monthNames: [
		"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
		"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"
	]
};

function __check(args)
{
	if (args != undefined && args.length != 1)
		debugger;
}

uDate.prototype.getFullYear		= function() { return this._date.getFullYear(); }
uDate.prototype.getUTCFullYear	= function() { return this._date.getUTCFullYear(); }
uDate.prototype.getMonth		= function() { return this._date.getUTCMonth(); }
uDate.prototype.getUTCMonth		= function() { return this._date.getUTCMonth(); }
uDate.prototype.getDay			= function() { return this._date.getUTCDay(); }
uDate.prototype.getUTCDay		= function() { return this._date.getUTCDay(); }
uDate.prototype.getHours		= function() { return this._date.getUTCHours(); }
uDate.prototype.getUTCHours		= function() { return this._date.getUTCHours(); }
uDate.prototype.getMinutes		= function() { return this._date.getUTCMinutes(); }
uDate.prototype.getUTCMinutes	= function() { return this._date.getUTCMinutes(); }
uDate.prototype.getSeconds		= function() { return this._date.getUTCSeconds(); }
uDate.prototype.getUTCSeconds	= function() { return this._date.getUTCSeconds(); }
uDate.prototype.getMilliseconds = function() { return this._date.getUTCMilliseconds(); }
uDate.prototype.getUTCMilliseconds = function() { return this._date.getUTCMilliseconds(); }
uDate.prototype.getMicroseconds = function() { return this._us; }
uDate.prototype.valueOf			= function() { return this._date.valueOf() * 1000 + this._us; }
uDate.prototype.getDate			= function() { return this._date.getUTCDate(); }
uDate.prototype.getUTCDate		= function() { return this._date.getUTCDate(); }
uDate.prototype.getTimezoneOffset = function() { return this._date.getTimezoneOffset(); }

uDate.prototype.toString		= function(v) { __check(arguments); return this._date.toString(v); }
uDate.prototype.toLocaleString	= function() { return this._date.toLocaleString(); }
uDate.prototype.propertyIsEnumerable = function(v) { __check(arguments); return this._date.toLocaleString(v); }
uDate.prototype.format 			= function (mask) { return dateFormat(this, mask, true); }

uDate.prototype.setFullYear		= function(v) { __check(arguments); this._date.setUTCFullYear(v); }
uDate.prototype.setMonth		= function(v) { __check(arguments); this._date.setUTCMonth(v); }
uDate.prototype.setDate			= function(v) { __check(arguments); this._date.setUTCDate(v); }
uDate.prototype.setHours		= function(v) { __check(arguments); this._date.setUTCHours(v); }
uDate.prototype.setMinutes		= function(v) { __check(arguments); this._date.setUTCMinutes(v); }
uDate.prototype.setSeconds		= function(v) { __check(arguments); this._date.setUTCSeconds(v); }
uDate.prototype.setMilliseconds = function(v) { __check(arguments); this._date.setUTCMilliseconds(v); }
uDate.prototype.setMicroseconds = function(v) {
	v = Math.round(v);
	this._us = v % 1000;
	if (v > 1000) {
		this._date.setUTCMilliseconds(this._date.getUTCMilliseconds() + Math.floor(v/1000));
	}
}
