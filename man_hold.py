import socket
import sys
import math
import time
import string
import threading

# 直连模式下，机器人默认 IP 地址为 192.168.2.1, 控制命令端口号为 40923
# USB模式下，机器人默认 IP 地址为 192.168.42.2, 控制命令端口号为 40923

address_ctrl = ("192.168.42.2", int(40923))  #控制命令
address_push = ("0.0.0.0", int(40924))  #推送消息

def send_and_recv(s,str):
    s.send(str.encode('utf-8'))
    print("send: "+str)
    buf = s.recv(1024)
    print("back: "+buf.decode('utf-8'))
    return buf

class Data:
    def __init__(self, raw):
        self.raw = raw
        substr = raw[15:-2]
        data_str_list = substr.split(',')
        self.cmd_id = int(data_str_list[0])
        self.len = int(data_str_list[1])
        self.mouse_press = int(data_str_list[2])
        self.mouse_x = int(data_str_list[3])
        self.mouse_y = int(data_str_list[4])
        self.seq = int(data_str_list[5])
        self.key_num = int(data_str_list[6])
        self.keys = []

        if not self.key_num == 0:
            for i in range(self.key_num):
                self.keys.append(int(data_str_list[i + 7]))

    def print_data(self):
        output = ""
        output += "cmd_id: " + str(self.cmd_id) + ","
        output += "len: " + str(self.len) + ","
        output += "mouse_press: " + str(self.mouse_press) + ","
        output += "mouse_x: " + str(self.mouse_x) + ","
        output += "mouse_y: " + str(self.mouse_y) + ","
        output += "seq: " + str(self.seq) + ","
        output += "key_num: " + str(self.key_num) + ","

        if self.key_num > 0:
            output += "keys: " + " ".join(map(str, self.keys))

        print(output)

def main():
    # 与机器人控制命令端口建立 TCP 连接
    sock_ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("Connecting sock_ctrl...")
    sock_ctrl.connect(address_ctrl)
    print("Connected!")

    # 与机器人消息推送端口建立 UDP 连接
    sock_push = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("Connecting sock_push...")
    sock_push.bind(address_push)
    print("Connected!")

    # 发送初始化控制命令给机器人
    send_and_recv(sock_ctrl, "command;")
    send_and_recv(sock_ctrl, "quit;")
    send_and_recv(sock_ctrl, "command;")    #退出sdk再重进是为了解决图传被卡住的bug（DJI的锅）
    send_and_recv(sock_ctrl, "robot mode free;")
    send_and_recv(sock_ctrl, "game_msg on;")

    data1 = Data("game msg push [0, 6, 0, 0, 0, 12, 1, 65];")
    loop_count = 0  #初始化计数变量
    while True:
        # 接收信息推送端口
        buf,_ = sock_push.recvfrom(1024)
        buf = buf.decode('utf-8')
        data0 = data1
        if buf.startswith("game"):
            data1 = Data(buf)
            
        #将数据转化为正负数
        data1.mouse_x = data1.mouse_x-255 if data1.mouse_x > 125 else data1.mouse_x
        data1.mouse_y = data1.mouse_y-255 if data1.mouse_y > 125 else data1.mouse_y
        #均值滤波
        data1.mouse_x = (data1.mouse_x+data0.mouse_x)/2
        data1.mouse_y = (data1.mouse_y+data0.mouse_y)/2

        #获取云台角度
        gb_atti = send_and_recv(sock_ctrl, "gimbal attitude ?;")
        gb_atti_list = gb_atti[:-2].decode('utf-8').split(' ')
        gb_pitch = float(gb_atti_list[0])
        gb_yaw = float(gb_atti_list[1])    

        move_speed = 150    #行走速度
        rush_speed = 500    #疾跑速度
        speed_tr = move_speed   #默认平移速度等于行走速度
        speed_th = 2.5  #底盘跟随云台速度比例
        x,y,z=0,0,0     #底盘运动三维速度
        tr_dir = 0      #底盘坐标系的运动方向

        if 16 in data1.keys:    #shift键
            speed_tr = rush_speed
        else:
            speed_tr = move_speed

        if(87 in data1.keys):   #W键
            x = speed_tr
        elif(83 in data1.keys): #S键
            x = -1*speed_tr
        else:
            x = 0

        if(68 in data1.keys):   #D键
            y = speed_tr
        elif(65 in data1.keys): #A键
            y = -1*speed_tr
        else:
            y = 0

        #将云台坐标系下运动方向转化为底盘坐标系下运动方向
        if y==0:
            tr_dir = gb_yaw
        elif x==0:
            tr_dir = gb_yaw+90
        else:
            tr_dir = gb_yaw+45

        x *= math.cos(math.radians(tr_dir))   #根据底盘坐标系运动方向计算X方向速度分量
        y *= math.sin(math.radians(tr_dir))   #根据底盘坐标系运动方向计算Y方向速度分量
        z = gb_yaw*speed_th     #根据云台与底盘夹角比例控制Z轴        

        if(loop_count==0):      #两种命令间隔发送，在同一循环内发送会造成卡顿与延迟
            send_and_recv(sock_ctrl, "gimbal speed p {0} y {1};".format(data1.mouse_y*28, data1.mouse_x*20))
        else:
            send_and_recv(sock_ctrl, "chassis wheel w1 {0} w2 {1} w3 {2} w4 {3};".format(x-y-z, x+y+z, x-y+z, x+y-z))

        #阻塞技能部分
        if 88 in data1.keys and 88 not in data0.keys:   #X键    底盘旋转180°（不精确，无闭环控制）
            send_and_recv(sock_ctrl, "game_msg off;")
            send_and_recv(sock_ctrl, "robot mode chassis_lead;")
            send_and_recv(sock_ctrl, "chassis wheel w1 {0} w2 {1} w3 {2} w4 {3};".format(-500, 500, 500, -500))
            time.sleep(0.3)
            send_and_recv(sock_ctrl, "chassis wheel w1 {0} w2 {1} w3 {2} w4 {3};".format(0, 0, 0, 0))
            send_and_recv(sock_ctrl, "robot mode free;")
            send_and_recv(sock_ctrl, "game_msg on;")
        if 90 in data1.keys and 90 not in data0.keys:   #Z键    云台旋转180°
            send_and_recv(sock_ctrl, "game_msg off;")
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 450;")
            time.sleep(0.4)
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 0;")
            send_and_recv(sock_ctrl, "game_msg on;")
        
        #循环技计数
        loop_count = 1 if loop_count==0 else 0
        print(" ")
if __name__ == '__main__':
    main()