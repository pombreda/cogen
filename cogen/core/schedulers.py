"""
Scheduling framework.

The scheduler handles the timeouts, run the operations and does very basic 
management of coroutines. Most of the heavy logic is in each operation class.
See: [Docs_CogenCoreEvents events] and [Docs_CogenCoreSockets sockets]
Most of those operations work with attributes we set in the scheduler.
"""

import collections
import datetime
import heapq
import weakref
import sys                
import errno
import select

from cogen.core.reactors import DefaultReactor
from cogen.core import events
from cogen.core import sockets
from cogen.core.util import debug, TimeoutDesc, priority
#~ getnow = debug(0)(datetime.datetime.now)
getnow = datetime.datetime.now

class DebugginWrapper:
    def __init__(self, obj):
        self.obj = obj
    
    def __getattr__(self, name):
        if 'append' in name:
            return debug(0)(getattr(self.obj, name))
        else:
            return getattr(self.obj, name)
class Timeout(object):
    """This wrapps a (op, coro) pair in weakreferences, extracts the timeout 
    value from the operation. We add instances of this class in the timeouts 
    heapq."""
    __slots__ = [
        'coro', 'op', 'timeout', 'weak_timeout', 
        'delta', 'last_checkpoint'
    ]
    def __init__(self, op, coro, weak_timeout=False):
        assert isinstance(op.timeout, datetime.datetime)
        self.timeout = op.timeout
        self.coro = weakref.ref(coro)
        self.op = weakref.ref(op)
        self.weak_timeout = weak_timeout
        if weak_timeout:
            self.last_checkpoint = getnow()
            self.delta = self.timeout - self.last_checkpoint
        
    def __cmp__(self, other):
        return cmp(self.timeout, other.timeout)    
    def __repr__(self):
        return "<%s@%s timeout:%s, coro:%s, op:%s, weak:%s, lastcheck:%s, delta:%s>" % (
            self.__class__.__name__, 
            id(self), 
            self.timeout, 
            self.coro(), 
            self.op(), 
            self.weak_timeout, 
            self.last_checkpoint, 
            self.delta
        )

class Scheduler(object):
    """Basic deque-based scheduler with timeout support and primitive 
    prioritisaiton parameters.
    
    Usage:
    {{{Scheduler(reactor=DefaultReactor, default_priority=priority.LAST, default_timeout=None)}}}
    
      * reactor: a reactor class to use
      * default_priority: a default priority option for operations that do not 
      set it. check [Docs_CogenCoreUtilPriority priority].
      * default_timeout: a default timedelta or number of seconds to wait for 
      the operation, -1 means no timeout.
    """
    def __init__(self, reactor=DefaultReactor, default_priority=priority.LAST, default_timeout=None, reactor_resolution=.01):
        self.timeouts = [] #heapq
        self.active = collections.deque()
        self.sigwait = collections.defaultdict(collections.deque)
        self.signals = collections.defaultdict(collections.deque)
        self.timewait = [] # heapq
        self.poll = reactor(self, reactor_resolution)
        self.default_priority = default_priority
        self.default_timeout = default_timeout
        self.running = False
    def __repr__(self):
        return "<%s@0x%X active:%s sigwait:%s timewait:%s poller:%s default_priority:%s default_timeout:%s>" % (
            self.__class__.__name__, 
            id(self), 
            len(self.active), 
            len(self.sigwait), 
            len(self.timewait), 
            self.poll, 
            self.default_priority, 
            self.default_timeout
        )
    def __del__(self):
        if hasattr(self, 'poll'):
            if hasattr(self.poll, 'scheduler'):
                del self.poll.scheduler
            del self.poll
    def add(self, coro, args=(), kwargs={}, first=True):
        """Add a coroutine in the scheduler. You can add arguments 
        (_args_, _kwargs_) to init the coroutine with."""
        assert callable(coro), "Coroutine not a callable object"
        coro = coro(*args, **kwargs)
        if first:
            self.active.append( (None, coro) )
        else:
            self.active.appendleft( (None, coro) )    
        return coro
       
    def run_timer(self):
        now = getnow() 
        while self.timewait and self.timewait[0].wake_time <= now:
            op = heapq.heappop(self.timewait)
            self.active.appendleft((op, op.coro))
    
    def next_timer_delta(self): 
        if self.timewait and not self.active:
            now = getnow()
            if now > self.timewait[0].wake_time:
                #looks like we've exceded the time
                return 0
            else:
                return (self.timewait[0].wake_time - now)
        else:
            if self.active:
                return 0
            else:
                return None
    
    def add_timeout(self, op, coro, weak_timeout):
        heapq.heappush(self.timeouts, Timeout(op, coro, weak_timeout))
    
    def handle_timeouts(self):
        now = getnow()
        #~ print '>to:', self.timeouts, self.timeouts and self.timeouts[0].timeout <= now
        while self.timeouts and self.timeouts[0].timeout <= now:
            timo = heapq.heappop(self.timeouts)
            op, coro = timo.op(), timo.coro()
            if op:
                #~ print timo
                if timo.weak_timeout and hasattr(op, 'last_update'):
                    if op.last_update > timo.last_checkpoint:
                        timo.last_checkpoint = op.last_update
                        timo.timeout = timo.last_checkpoint + timo.delta
                        heapq.heappush(self.timeouts, timo)
                        continue
                throw = op.cleanup(self, coro)
                
                if not op.finalized and coro and coro.running and throw:
                    self.active.append((
                        events.CoroutineException((
                            events.OperationTimeout, 
                            events.OperationTimeout(op)
                        )), 
                        coro
                    ))
    
    def process_op(self, op, coro):
        "Process a (op, coro) pair and return another pair. Handles exceptions."
        if op is None:
            if self.active:
                self.active.append((op, coro))
            else:
                return op, coro 
        else:
            try:
                result = op.process(self, coro) or (None, None)
            except:
                result = events.CoroutineException(sys.exc_info()), coro
            return result
        return None, None
    
    def run(self):
        """This is the main loop.
        This loop will exit when there are no more coroutines to run or stop has
        been called.
        """
        self.running = True
        urgent = None
        while self.running and (self.active or self.poll or self.timewait or urgent):
            if self.active or urgent:
                op, coro = urgent or self.active.popleft()
                urgent = None
                while True:
                    op, coro = self.process_op(coro.run_op(op), coro)
                    if not op and not coro:
                        break  
                    
            if self.poll:
                try:
                    urgent = self.poll.run(timeout = self.next_timer_delta())
                except (OSError, select.error), exc:
                    if exc[0] != errno.EINTR:
                        raise
                #~ if urgent:print '>urgent:', urgent
            if self.timewait:
                self.run_timer()
            if self.timeouts: 
                self.handle_timeouts()
                
            #~ print 'active:  ',len(self.active)
            #~ print 'poll:    ',len(self.poll)
            #~ print 'timeouts:',len(self.timeouts)
            #~ print 'running: ',self.running
    def stop(self):
        self.running = False
