import socket
import struct
import threading
import time
import random
import queue

'''
    total_packet_num is the receive buffer (unit: packet), and the MTU is 1000. Therefore total buffer size in byte is 
    5000*1000 = 5*10^6 (bytes) = 5MB
    net_window is the congestion window size
'''

init_hdr = 'ii'
send_hdr = ''
normal_hdr = 'iiiiii'
ack_hdr = 'iiii'
recv_buf = []
MTU = 1000
send_flag = True
total_packet_num_me = 5000
total_packet_num_you = 5000
net_window = 50
stream_buf = []  
ack_buf = [] 
reture_buffer = []
stream_maxnum = {}
t = None
tr = None
send_buf = queue.Queue()

for i in range(10):
    stream_buf.append([])

def Recv(socket):

    socket.settimeout(3)
    global recv_buf
    global stream_buf
    global total_packet_num_me
    global stream_maxnum
    global reture_buffer
    global ack_buf
    global net_window
    global total_packet_num_you
    global send_flag

    start = time.time()
    while send_flag:
        
        try:
            data , addr = socket.recvfrom(1024)
            start = time.time()
        except:
            data = None

        if data != None:
            Type = struct.unpack('i', data[0:4])[0]
            # print('t: ',Type)
            if Type == 0:
                Type, sid, num, offset, Len, fin = struct.unpack(normal_hdr, data[0:24])
                # print(Type, sid, num, offset, len, fin)
                payload = data[24:].decode()
                # print('p: ',payload)

                
                if total_packet_num_me > 0:
                    if (num, offset, payload) not in stream_buf[sid]:
                        # print('get: ', sid, num)
                        # print('receive packet( streamid, pkt_num ) = ', sid, num)
                        stream_buf[sid].append((num, offset, payload))
                        if fin == 1:
                            stream_maxnum[sid] = num + 1

                        if sid in stream_maxnum and len(stream_buf[sid]) == stream_maxnum[sid]:
                            stream_buf[sid].sort(key=lambda a: a[0])
                            concat = ''
                            for i in range(len(stream_buf[sid])):
                                concat += stream_buf[sid][i][2]
                            # print(sid, 'data: ', concat)
                            reture_buffer.append((sid, concat.encode()))
                        total_packet_num_me -= 1
                        
                    
                    ret_pkt = struct.pack(ack_hdr, 1, sid, num, total_packet_num_me)
                    # print('ack: ', sid, num)
                    socket.sendto(ret_pkt, addr)
                else:
                    print('no space')

            if Type == 1:
                Type, sid, num, con_win = struct.unpack(ack_hdr, data[0:16])
                if (sid, num) not in ack_buf:
                    # print('ack: ', sid, num)
                    ack_buf.append((sid, num))
                    # print(ack_buf)
                    net_window += 1
                total_packet_num_you = con_win


        # print('recv_buf: ', recv_buf)

def Send(socket, addr):
    
    global send_flag
    global send_buf
    global net_window
    global total_packet_num_you
    while send_flag:
        time.sleep(0.1)
        # print('congestion control: ', net_window)
        # window = min(min(len(send_buf), total_packet_num), net_window)
        window = min(min(send_buf.qsize(), total_packet_num_you), net_window)
        window = max(window, 1)
        # print('window: ', window)
        for i in range(window):

            if send_buf.empty():
                break
            # print((send_buf[i][0], send_buf[i][1]))
            top = send_buf.get()
            # print(top)
            if (top[0], top[1]) in ack_buf:
                
                # ack_buf.remove((send_buf[i][0], send_buf[i][1]))
                window -= 1
                i-= 1
            else:
                if time.time() - top[3] > 0.3:
                    net_window = int(net_window/2) + 1
                    # print('send: ', (top[0], top[1]))
                    cur_t = time.time()
                    # print('send:', top[0], top[1])
                    # print('send packet (stream id, pkt_num ) = :', top[0], top[1])
                    socket.sendto(top[2], addr)
                    send_buf.put((top[0], top[1], top[2], time.time()))   
                else:
                    send_buf.put((top[0], top[1], top[2], top[3]))  
            


class QUICClient:
    client_socket = ""
    addr = ''
    global send_buf
    global reture_buffer
    global total_packet_num_me
    global t
    global tr
    def connect(self, socket_addr: tuple[str, int]):
        """connect to the specific server"""
        self.addr = socket_addr
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_socket.settimeout(0.3)
        hdr = struct.pack(init_hdr, -1, 1000)
        while True:    
            self.client_socket.sendto(hdr, socket_addr)
            try:
                data, address = self.client_socket.recvfrom(1024)
                
            except:
                data = None

            if data != None:    
                if data.decode() == 'yes':
                    print('connected')
                    hdr = struct.pack(init_hdr, -2, 1000)
                    for i in range(10):
                        self.client_socket.sendto(hdr, socket_addr)
                    break

        t = threading.Thread(target = Send, args=(client.client_socket, client.addr, ))
        t.start()
        tr = threading.Thread(target = Recv, args=(client.client_socket,))
        tr.start()
        pass
    











    def send(self, s_id: int, s: bytes):
        """call this method to send data, with non-reputation stream_id"""
        chk = int((len(s)-1) / MTU) + 1
        for i in range(chk):
            if i != chk-1:
                s_data = struct.pack(normal_hdr, 0, s_id, i, i*MTU, MTU, 0)
                payload_en = s[i*MTU: (i+1)*MTU]
            else:
                s_data = struct.pack(normal_hdr, 0, s_id, i, (i)*MTU, len(s)-(i)*MTU, 1)
                payload_en = s[i*MTU: ]
            send_buf.put((s_id, i, s_data+payload_en, time.time()-10))
            # send_buf.append((s_id, i, s_data+payload_en, time.time()-10))

        pass
    
    def recv(self) -> tuple[int, bytes]: # stream_id, data
        global total_packet_num_me
        """receive a stream, with stream_id"""
        ret = ''
        while True:
            if len(reture_buffer) > 0:
                ret = reture_buffer[0]
                total_packet_num_me += stream_maxnum[ret[0]]
                reture_buffer.pop(0)
                break
        return ret

        pass
    
    def close(self):
        """close the connection and the socket"""
        time.sleep(30)    ############### need to sleep enough time to let client and server send all of their packet
        global send_flag
        send_flag = False
        self.client_socket.close()
        print('close connection')
        pass






if __name__ == "__main__":
    client = QUICClient()
    client.connect(("127.0.0.1", 30000))
    recv_id, recv_data = client.recv()
    print(recv_data.decode("utf-8")) # SOME DATA, MAY EXCEED 1500 bytes
    recv_id, recv_data = client.recv()
    print(recv_data.decode("utf-8")) # SOME DATA, MAY EXCEED 1500 bytes

    client.send(2, b"Hello Server!")
    client.send(1, b"21312312423424")

    client.close()