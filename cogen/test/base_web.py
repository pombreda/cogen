__doc_all__ = []

import unittest
import sys
import exceptions
import datetime
import time
import random
import threading
import thread
import wsgiref.validate
import httplib
from cStringIO import StringIO

from cogen.common import *
from cogen.web import wsgi, async

sys.setcheckinterval(0)
#~ httplib.HTTPConnection.debuglevel = 10

class WebTest_Base:
    middleware = [wsgiref.validate.validator, async.sync_input]
    def setUp(self):
        self.local_addr = ('localhost', random.randint(10000,20000))
        #~ print "http://%s:%s/"%self.local_addr
        def run():
            try:
                app = self.app
                for wrapper in self.middleware:
                    app = wrapper(app)
                self.sched = Scheduler(default_priority=self.prio, 
                                        reactor=self.poller) 
                server = wsgi.WSGIServer(self.local_addr, app, self.sched) 
                self.sched.add(server.serve)
                self.sched.run()
            except:
                import traceback
                traceback.print_exc()
            
        self.m_run = threading.Thread(target=run)
        self.m_run.start()
        time.sleep(0.1)
        self.conn = httplib.HTTPConnection(*self.local_addr)
        self.conn.connect()
        
        #~ self.conn.set_debuglevel(10)
    def tearDown(self):
        self.conn.close()
        self.sched.stop()
        self.m_run.join()
        
        
