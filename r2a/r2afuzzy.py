from base.whiteboard import Whiteboard
from player.parser import *
from r2a.ir2a import IR2A
from player.player import *
from math import sqrt
from statistics import mean
import bisect

class R2AFuzzy(IR2A):

    def __init__(self, id):
        IR2A.__init__(self, id)
        self.throughputs = []
        self.request_time = 0
        self.qi = []
        self.buffers = []
        self.resolutions = []
        self.T = 35
        self.TWO_THIRDS_T = (2 * self.T) /3
        self.FOUR_T = 4 * self.T

    def handle_xml_request(self, msg):
        self.request_time = time.perf_counter()
        self.send_down(msg)

    def handle_xml_response(self, msg):
        parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = parsed_mpd.get_qi()

        self.send_up(msg)

    def handle_segment_size_request(self, msg):
        self.buffer = self.whiteboard.get_playback_buffer_size()
        self.request_time = time.perf_counter()

        next_resolution = self.qi[0]

        if len(self.buffer) > 0: 
            f = self.output_controller(self.buffer)
            avarage_thoughputs = mean(self.throughputs[-3:])
            avarage_resolutions = mean(self.resolutions[-3:])
            next_bit_rate = f * avarage_thoughputs
            index = bisect.bisect(self.qi, next_bit_rate)
            next_resolution = self.qi[index - 1]
            current_resolution = self.resolutions[-1]            
            estimated_buffer = 'nao interessa'

            print(f'+++++++++++++ self.resolutions[-5:],mean(self.resolutions[-5:]), next_resolution, estimated_buffer')
            print(f'+++++++++++++ {self.resolutions[-5:],mean(self.resolutions[-5:]), next_resolution, estimated_buffer}')

            estimated_buffer_next  = self.buffer_time + ((self.throughputs[-1] / 3) / next_resolution) * 60
            estimated_buffer_previous = self.buffer_time + ((self.throughputs[-1] / 3) / current_resolution) * 60

            if next_resolution > current_resolution:
                if estimated_buffer_next < self.T:
                    next_resolution = current_resolution
                    print(f'!!!!!!!!!!!! OLHA O BUFFER: {estimated_buffer}')
            elif next_resolution < current_resolution:
                if estimated_buffer_previous > self.T:
                    next_resolution = current_resolution 
                    print(f'!!!!!!!!!!!! Caso 2')

            print(f'>>>>>>>>>>>>> f, self.buffer_time, current_throughput, avarage_thoughputs, current_resolution, next_bit_rate, index, next_resolution')
            print(f'>>>>>>>>>>>>>{f, self.buffer_time, self.throughputs[-1], avarage_thoughputs, current_resolution, next_bit_rate, index, next_resolution}')

        msg.add_quality_id(next_resolution)
        self.resolutions.append(next_resolution)
        self.send_down(msg)

    def linear_function(self,x0,x1, diff = False):
        a  = 1 / (x1 - x0)
        b = - (a * x0)
        if diff:
            return a * self.diff + b
        return a * self.buffer_time + b

    def output_controller(self, buffer):
        self.buffer_time = buffer[-1][1]
        try:
            previous_buffer_time = self.buffers[-1]
        except:
            previous_buffer_time = self.buffer_time
        self.buffers.append(self.buffer_time)
        FACTORS = {'N2':0.25,'N1':0.5, 'Z':1, 'P1':1.5, 'P2':2}
        self.short, close, self.long, falling, steady, rising = 0,0,0,0,0,0

        if(self.buffer_time <= self.TWO_THIRDS_T):
            short = 1
        elif(self.buffer_time >= self.T):
            short = 0
        else:
            short = self.linear_function(self.T, self.TWO_THIRDS_T)
        
        if(self.buffer_time <= self.TWO_THIRDS_T or self.buffer_time >= self.FOUR_T):
            close = 0
        elif(self.buffer_time <= self.T):
            close = self.linear_function(self.TWO_THIRDS_T, self.T)
        else:
            close = self.linear_function(self.FOUR_T, self.T)

        if(self.buffer_time <= self.T):
            long = 0
        elif(self.buffer_time >= 4*self.T):
            long = 1
        else:
            long = self.linear_function(self.T, self.FOUR_T)

        self.diff = self.buffer_time - previous_buffer_time

        if self.diff <= -(self.TWO_THIRDS_T):
            falling = 1
        elif self.diff >= 0:
            falling = 0
        else:
            falling = self.linear_function(0, - self.TWO_THIRDS_T, True)

        if self.diff <= -(self.TWO_THIRDS_T) or self.diff >= self.FOUR_T:
            steady = 0
        elif self.diff <= 0:
            steady = self.linear_function(-self.TWO_THIRDS_T, 0, True)
        else:
            steady = self.linear_function(self.FOUR_T, 0, True)

        if self.diff <= 0:
            rising = 0
        elif self.diff >= self.FOUR_T:
            rising = 1
        else:
            rising = self.linear_function(0, self.FOUR_T, True)

        print(f"*******************previous_buffer_time, self.buffer_time")
        print(f"*******************{previous_buffer_time, self.buffer_time}")
        print(f'*******************.short, close, long')
        print(f'*******************.{short, close, long}')
        print(f'*******************.falling, steady, rising')
        print(f'*******************.{falling, steady, rising}')
        
        rules = []

        rules.append(min(short, falling)) 
        rules.append(min(close, falling)) 
        rules.append(min(long, falling)) 
        rules.append(min(short, steady)) 
        rules.append(min(close, steady)) 
        rules.append(min(long, steady)) 
        rules.append(min(short, rising)) 
        rules.append(min(close, rising)) 
        rules.append(min(long, rising))

        I =  sqrt(rules[8]**2)
        SI = sqrt(rules[5]**2 + rules[7]**2)        
        NC = sqrt(rules[2]**2 + rules[4]**2 + rules[6]**2)        
        SR = sqrt(rules[1]**2 + rules[3]**2)        
        R = sqrt(rules[0]**2)        

        f_num = FACTORS['N2'] * R + FACTORS['N1'] * SR + FACTORS['Z'] * NC + FACTORS['P1'] * SI + FACTORS['P2'] * I  
        f_den = SR + R + NC + SI + I

        return f_num / f_den

    def handle_segment_size_response(self, msg):
        t = time.perf_counter() - self.request_time
        # Vazão
        #self.vazao[self.qi] = msg.get_bit_length() / t
        self.throughputs.append(msg.get_bit_length() / t)
        #self.Ts[self.Tsi] = (msg.get_bit_length() / t) 
        print(f'================================ {self.throughputs[-1]}')
        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass
