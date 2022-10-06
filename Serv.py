#Author Thorold Tronrud
#Software Engineer @ StarFish Medical
#* ------------------------------------------------------------------------------*
#* MIT License                                                                   *
#*                                                                               *
#* Copyright (c) 2018 Rafael de Moura Moreira                                    *
#*                                                                               *
#* Permission is hereby granted, free of charge, to any person obtaining a copy  *
#* of this software and associated documentation files (the "Software"), to deal *
#* in the Software without restriction, including without limitation the rights  *
#* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     *
#* copies of the Software, and to permit persons to whom the Software is         *
#* furnished to do so, subject to the following conditions:                      *
#*                                                                               *
#* The above copyright notice and this permission notice shall be included in all*
#* copies or substantial portions of the Software.                               *
#*                                                                               *
#* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    *
#* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      *
#* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   *
#* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER        *
#* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, *
#* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE *
#* SOFTWARE.                                                                     *
#*-------------------------------------------------------------------------------*



#If we want, HTTPS can be used by the gateways, though we'll need to set up certificates for these, too...
#use https://www.pwndefend.com/2020/02/04/tech-tip-simple-python3-https-server/ for HTTPS reference
#or https://stackoverflow.com/questions/61348501/tls-ssl-socket-python-server
#https://gist.github.com/mdonkers/63e115cc0c79b4f6b8b3a6b797e485c7#:~:text=def%20do_POST%20%28self%29%3A%20content_length%20%3D%20int%20%28self.%20headers,read%20%28content_length%29%20%23%20%3C---%20Gets%20the%20data%20itself for version with do_POST

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
import socket #allows us to get the local IP
import queue #threadsafe queues
import numpy as np

#What ports are assigned to gateways?
#Combined with LAN_IP, we can monitor all gateways on the local network
GATEWAY_PORTS = [1337,]
API_PORT = 1234
#We also gather the gateway MAC address, so we can use that instead of port# if necessary

#How long do we want our memory of previous mac-beacon-rssi data to be?
#How many previous entries do we want to store? e.g. for getting average RSSI
MAX_MEMORY = 16
PX_PER_M = 24
#Use a class/object to ensure the running variable is shared
#Necessary for non-blocking IO thread to end master-server mainloop
#Also spins up threads for running servers

class ServerMonitor:
    def __init__(self, quiet_mode = False):
        #state variable we check in our main loop
        self.server_running = True
        self.quiet_mode = quiet_mode
        #Storage of servers and threads
        #We need a list of POST servers (one for each port), but only one API server
        self.http_servers = []
        self.serv_threads = []
        self.API_server = None
        self.api_thread = None
        #A queue for the threads to place their beacon reports into
        #so we don't have a bunch of threads all playing with arrays
        self.report_q = queue.Queue()
        self.data = {} #Dictionary of data recv'd at each port
        self.LaunchAPI() #we'll launch the API as soon as we start the monitor
    #end everything
    def EndServers(self):
        print("Server close queued")
        self.server_running = False     
        for http_serv in self.http_servers:
            http_serv.CloseServer()  
        if self.API_server != None:
            self.API_server.CloseServer()
            
    #A single gateway sees a single beacon
    #This is the reporting function - so we're using a threadsafe queue
    def AddData(self, DATA, pnum):
        self.report_q.put((DATA, pnum, time.time()))
    #Is a thread alive?
    #Try to join it, with zero timeout. If it fails, it's doing something
    def ThreadAlive(self,thr):
        thr.join(timeout=0.0)
        return thr.is_alive()
    #Main-loop hander for queue
    #work on all the info dumped into the queue storage to
    #be processed
    def QueueHandle(self):
        #if API thread has died for some reason (aka error), restart
        if not self.ThreadAlive(self.api_thread):
            self.LaunchAPI()
            print("API relaunched!")
        #parse through all items added to queue
        while not self.report_q.empty():
            cont,pnum,t = self.report_q.get()
            #Just add the data to the list we're storing
            if pnum not in self.data.keys():
                self.data[pnum] = [] #create the list
            self.data[pnum].append(cont)
            #We don't want a memory leak, though... Delete oldest data if we're getting too long
            if len(self.data[pnum]) > MAX_MEMORY:
                #print("Trimming array!")
                self.data[pnum].pop(0) #pop the oldest value out of the list
    #Test for how well threads can report back to this monitor
    def MonitorPrint(self, msg, port = 0, mac = 0):
        if self.quiet_mode:
            return
        print("P#%d M#%s"%(port,mac) + "\t" + msg)

    #Add a server to the list,
    #and spin up a request handling loop
    #track the thread, too
    def AddServer(self, serv):
        self.http_servers.append(serv)
        th = threading.Thread(target=ContinuouslyHandleRequests, args=(serv, self,))
        th.daemon = True #we want them to close with the master thread
        self.serv_threads.append(th)
        th.start()
        print("Started server for port %d"%serv.port)
    #Launch the API server
    def LaunchAPI(self):
        self.API_server = http_server(LAN_IP,API_PORT,ServerMonitorAPI,self)
        th = threading.Thread(target=ContinuouslyHandleRequests, args=(self.API_server, self,))
        th.daemon = True
        self.api_thread = th
        self.api_thread.start()
    
    #Add implementation-specific functions below
    #things that manipulate the entire data set aggregated
    #in this controller class
    #
    def TestGetData(self, pnum=-1):
        if(pnum <= 0 or pnum not in self.data.keys()):
            return "NULL"
        #If the data exists, dump it as json
        return json.dumps(self.data[pnum])
    #   
    ##
    
#have each server handled simultaneously to prevent
#blocking by inactive gateway ports
#these threads are spun up by the monitor
def ContinuouslyHandleRequests(httpserv,monitor):
    while monitor.server_running:
        httpserv.HandleRequests()             
            
#keyboard IO handled as a thread to keep it non-blocking
#tells the server monitor to end all the servers
def IONonBlock(serve_monitor):
    no_close_queued = True #flag to prevent double-appearance of input prompt
    while no_close_queued:
        val = input("'quit' or 'q' to terminate program\n")
        if(val == "q" or val == "quit"):
            serve_monitor.EndServers()
            no_close_queued = False
        #add additional conditions here for console
        #control over server master
        
#Hacky little http_server class that allows us to sneak
#extra parameters into the response handler class (e.g. port # and monitor ref)
#The parameter is essentially static (One change modifies it for all instances)
class http_server:
    #Takes LAN IP, port, ref to POST handler, ref to monitor
    def __init__(self, LAN_IP, port, handler, monitor):
        self.port = port
        self.LAN_IP = LAN_IP
        handler.monitor = monitor
        self.server = HTTPServer((LAN_IP, port),handler)
    def HandleRequests(self):
        self.server.handle_request()
    def CloseServer(self):
        self.server.server_close()
        
        
#Server class to handle an individual port of input
#It gets the POST data differentiated by port #
#and splits the content into individual devices and RSSIs
#
#Has its own port# and monitor reference for feeding info back to the
#monitor
class Server(BaseHTTPRequestHandler):
    monitor = None
    def do_POST(self): 
        #Get the Host string, split to get port number
        hoststr = self.headers['Host']
        port_num = int(hoststr.split(":")[1])
        #Get content length to read from rfile
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        #unpack content from raw POST data
        
        #JSON branch -- remove if unneeded
        content = json.loads(post_data)
        self.monitor.AddData(content["data"], port_num)
        #Debug print for the packet
        #can remove
        self.monitor.MonitorPrint(str(content), port = port_num, mac = hoststr)
        
        self.wfile.write(b"HTTP/1.1 200 OK\n\n")
    

#The API server for the monitor class.
#This server accepts GET requests, slaps a "correct" header on,
#and reacts to the path fed through http.
#This will be how external clients interface with the server,
#at least until a database is set up
class ServerMonitorAPI(BaseHTTPRequestHandler):
    monitor = None
    #Triangulation calculation
    #Can use estimated distances for R1,2,3
    #pos are the positions of three receivers
    def Tri_Calc(self, R1,R2,R3,pos1,pos2,pos3):
        D1 = R1**2 - pos1[0]**2 - pos1[1]**2
        D2 = R2**2 - pos2[0]**2 - pos2[1]**2
        D3 = R3**2 - pos3[0]**2 - pos3[1]**2
        
        twoy = ((D2-D3)/(pos3[0]-pos2[0])) - ((D2-D1)/(pos1[0]-pos2[0]))
        denom = ((pos2[1]-pos1[1])/(pos1[0]-pos2[0])) - ((pos2[1]-pos3[1])/(pos3[0]-pos2[0]))
        twoy = twoy/denom
        twox = ((D2-D1)/(pos1[0]-pos2[0])) + twoy*((pos2[1]-pos1[1])/(pos1[0]-pos2[0]))
        _x = twox/2
        _y = twoy/2
        return (_x,_y)
        
    #We're gonna use the request path (self.path) to indicate which device we want to find
    #TODO:
    #Change GET path to GET [ip]:[port]/AssetTracking/[REQUEST]
    def do_GET(self):
        try:
            resp = 200
            parsed_path = self.path.strip("/")
            parsed_path_list = parsed_path.split("/")
            #do stuff with different "path"s -- can use as buttons to send specific API commands
            #output must be to self.wfile.write 
            self.wfile.write(b"HTTP/1.1 200 OK\n\n")
            ret_str = ""
            #just echo the path back for now
            ret_str = self.monitor.MonitorPrint(parsed_path)
            #Add conditions for more nuanced behaviour
                
            self.wfile.write(ret_str.encode('utf-8')) #Just echo the MAC/path back
            self.send_response(resp)
        except Exception as e:
            self.send_error(500,e)
    
    def do_POST(self):
        #We'll probably want some sort of authentication here later!!
        ##
        #Get the Host string, split to get port number
        hoststr = self.headers['Host']
        parsed_path = self.path.strip("/")
        port_num = int(hoststr.split(":")[1])
        #Get content length to read from rfile
        content_length = int(self.headers['Content-Length'])
        #Read the data
        post_data = self.rfile.read(content_length)
        post_data_dict = json.loads(post_data)
        if "port" not in post_data_dict.keys():
            post_data_dict["port"] = -1
        ret_d = {}
        try:
            if parsed_path == "path-to-some/CONFIG":
                #add to the return dictionary
                #which we'll format for JSON
                ret_d["success"] = "true" 
                #Get the test data
                ret_d["data"] = self.monitor.TestGetData(post_data_dict["port"])
            else:
                ret_d["success"] = "false"
        except Exception as e:
            ret_d["success"] = "false"
            ret_d["error"] = str(e)
            
        ret_str = json.dumps(ret_d)  
        
        self.wfile.write(b"HTTP/1.1 200 OK\n\n")
        self.wfile.write(ret_str.encode('utf-8'))
        self.send_response(200) #success

#Main thread!
h_name = socket.gethostname()
LAN_IP = socket.gethostbyname(h_name) #get the LAN info, so we don't need to hardcode it
print("LAN info: ",h_name,", ",LAN_IP)    
#Start the monitor, give it a quirky name
guilty_spark = ServerMonitor(quiet_mode = True)
#go through each defined gateway port and start a server monitoring it
for p in GATEWAY_PORTS:
    #register the gateway server with the monitor (and refer to the monitor for the server)
    guilty_spark.AddServer(http_server(LAN_IP,p,Server,guilty_spark))
    
#Start the non-blocking IO thread
#So we can control the server through CLI if needed
nbio_thread = threading.Thread(target=IONonBlock, args=(guilty_spark,))
nbio_thread.daemon = True #make thread die with this program
nbio_thread.start() #start

#we just need something spinning in the background
while guilty_spark.server_running:
    #Queue handler
    guilty_spark.QueueHandle()
    #we can sleep at a "long" (CPU-wise) interval that is also "short" (human-wise)
    #to avoid just tossing junk at the CPU while the threads do everything
    #useful
    time.sleep(0.5)
#Make sure to close the servers
guilty_spark.EndServers()