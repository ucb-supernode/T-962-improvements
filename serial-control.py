#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Log the temperatures reported by the oven in a live plot and
# in a CSV file.
#
# Requires
# python 2.7
# - pyserial (python-serial in ubuntu, pip install pyserial)
# - matplotlib (python-matplotlib in ubuntu, pip install matplotlib)
#

import csv
import datetime
import serial
import sys
from time import time

import matplotlib
matplotlib.use('WXAgg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# settings
#
FIELD_NAMES = 'Time,Temp0,Temp1,Temp2,Temp3,Set,Actual,Heat,Fan,ColdJ,Mode'
TTYs = ('COM1', 'COM2', 'COM3', 'COM4', 'COM5',
        '/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB2',
        '/dev/tty.usbserial',
        '/dev/tty.PL2303-00002014', '/dev/tty.PL2303-00001014')
BAUD_RATE = 115200

logdir = 'logs/'

DEBUG = open('debug_output', 'w+')

MAX_X = 470
MAX_Y_temperature = 300
MAX_Y_pwm = 260
#
# end of settings

def timestamp(dt=None):
    if dt is None:
        dt = datetime.datetime.now()

    return dt.strftime('%Y-%m-%d-%H%M%S')


def logname(filetype, profile, timestamp):
    return '%s%s-%s.%s' % (
        logdir,
        timestamp,
        profile.replace(' ', '_').replace('/', '_'),
        filetype
    )


def get_tty():
    for devname in TTYs:
        try:
            port = serial.Serial(devname, baudrate=BAUD_RATE)
            print 'Using serial port %s' % port.name
            return port
        except:
            pass

    return None


class Line(object):
    def __init__(self, axis, key, label=None):
        self.xvalues = []
        self.yvalues = []

        self._key = key
        self._line, = axis.plot(self.xvalues, self.yvalues, label=label or key)

    def add(self, log):
        self.xvalues.append(log['Time'])
        self.yvalues.append(log[self._key])

        self.update()

    def update(self):
        self._line.set_data(self.xvalues, self.yvalues)

    def clear(self):
        self.xvalues = []
        self.yvalues = []

        self.update()

class Log(object):
    profile = ''

    def __init__(self):
        self.init_plot()
        self.clear_logs()

    def clear_logs(self):
        self.raw_log = []
        map(Line.clear, self.lines)
        self.mode = ''

    def init_plot(self):
        plt.ion()

        gs = gridspec.GridSpec(2, 1, height_ratios=(4, 1))
        fig = plt.figure(figsize=(7, 5))

        axis_upper = fig.add_subplot(gs[0])
        axis_lower = fig.add_subplot(gs[1], sharex=axis_upper)
        plt.subplots_adjust(hspace=0.05, top=0.95, bottom=0.10, left=0.10, right=0.95)

        # setup axis for upper graph (temperature values)
        axis_upper.set_ylabel(u'Temperature [°C]')
        axis_upper.set_xlim(-5, MAX_X)
        axis_upper.set_ylim(-5, MAX_Y_temperature)
        plt.setp( axis_upper.get_xticklabels(), visible=False)

        # setup axis for lower graph (PWM values)
        axis_lower.set_xlim(-5, MAX_X)
        axis_lower.set_ylim(-5, MAX_Y_pwm)
        axis_lower.set_ylabel('PWM value')
        axis_lower.set_xlabel('Time [s]')

        # select values to be plotted
        self.lines = [
            Line(axis_upper, 'Actual'),
            Line(axis_upper, 'Temp0'),
            Line(axis_upper, 'Temp1'),
            Line(axis_upper, 'Set', u'Setpoint'),
            Line(axis_upper, 'ColdJ', u'Coldjunction'),
        #   Line(axis_upper, 'Temp2'),
        #   Line(axis_upper, 'Temp3'),

            Line(axis_lower, 'Fan'),
            Line(axis_lower, 'Heat', 'Heater')
        ]

        axis_upper.legend()
        axis_lower.legend()
        plt.draw()
        plt.pause(0.1)

        self.axis_upper = axis_upper
        self.axis_lower = axis_lower


    def save_logfiles(self):
        if len(self.raw_log) < 100:
            print 'Not saving log (too short)'
            return

        now = timestamp()
        print 'Saved log in %s ' % logname('csv', self.profile, now)
        plt.savefig(logname('png', self.profile, now))
        plt.savefig(logname('pdf', self.profile, now))

        with open(logname('csv', self.profile, now), 'w+') as csvout:
            writer = csv.DictWriter(csvout, FIELD_NAMES.split(','))
            writer.writeheader()

            for l in self.raw_log:
                writer.writerow(l)

    def parse(self, line):
        values = map(str.strip, line.split(','))
        # Convert all values to float, except the mode
        values = map(float, values[0:-1]) + [values[-1], ]

        fields = FIELD_NAMES.split(',')
        if len(values) != len(fields):
            raise ValueError('Expected %d fields, found %d' % (len(fields), len(values)))

        return dict(zip(fields, values))

    def process_log(self, logline):
        print >>DEBUG, logline

        # ignore 'comments'
        if logline.startswith('#'):
            return

        # parse Profile name
        if logline.startswith('Starting reflow with profile: '):
            self.profile = logline[30:].strip()
            return

        if logline.startswith('Selected profile'):
            self.profile = logline[20:].strip()
            return

        try:
            log = self.parse(logline)
            print >>DEBUG, log
        except ValueError, e:
            if len(logline) > 0:
                print >>DEBUG, '!!', logline
            return

        if 'Mode' in log:
            # clean up log before starting reflow
            if self.mode == 'STANDBY' and log['Mode'] in ('BAKE', 'REFLOW'):
                self.clear_logs()

            # save png graph an csv file when bake or reflow ends.
            if self.mode in ('BAKE', 'REFLOW') and log['Mode'] == 'STANDBY':
                self.save_logfiles()

            self.mode = log['Mode']
            if log['Mode'] == 'BAKE':
                self.profile = 'bake'

            self.axis_upper.set_title('Profile: %s Mode: %s ' % (self.profile, self.mode))

        if 'Time' in log and log['Time'] != 0.0:
            if 'Actual' not in log:
                return

            # update all lines
            map(lambda x: x.add(log), self.lines)
            self.raw_log.append(log)


        # update view
        plt.draw()
        plt.pause(0.001)

def logging_only():
    log = Log()

    port = get_tty()
    if not port:
        return
    try:
        while True:
            serial_line = port.readline().strip()
            log.process_log(serial_line)
    except Exception:
        sys.exit(0)
    finally:
        port.close()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            port = serial.Serial(sys.argv[1], baudrate=BAUD_RATE)
            TTYs = [sys.argv[1]]
        except:
            pass

    print 'Logging reflow sessions...'
    logging_only()
