import threading
import time
import socket
import math
import sys
import string
import serial
from queue import Queue

# 直连模式下，机器人默认 IP 地址为 192.168.2.1, 控制命令端口号为 40923
# USB模式下，机器人默认 IP 地址为 192.168.42.2, 控制命令端口号为 40923

address_ctrl = ("192.168.42.2", int(40923))  #控制命令
address_push = ("0.0.0.0", int(40924))  #推送消息

# 设置串口参数
# serial_port = "COM3"  # 请根据你的系统和连接方式修改串口名称
# baud_rate = 115200
# ser = serial.Serial(serial_port, baud_rate)

def send_and_recv(s, string):
    with send_recv_lock:
        s.send(string.encode('utf-8'))
        print("send: " + string)
        buf = s.recv(1024)
        print("back: " + buf.decode('utf-8'))
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

class GimbalData:
    def __init__(self, raw):
        substr = raw[21:-1]   # 消息推送
        data_str_list = substr.split(' ')
        self.pitch = float(data_str_list[0])
        self.yaw = float(data_str_list[1])
        
    def print_data(self):
        print(f"pitch:{self.pitch}° yaw:{self.yaw}°")

class UI:
    def __init__(self,mode):
        self.mode = mode
        self.is_setting = False

# 创建两个锁对象
lock = threading.Lock()
send_recv_lock = threading.Lock()
blaster_event = threading.Event()
blaster_event.set()


# 与机器人控制命令端口建立 TCP 连接
sock_ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print("Connecting sock_ctrl...")
sock_ctrl.connect(address_ctrl)
print("Connected!")

# 与机器人消息推送端口建立 TCP 连接
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
send_and_recv(sock_ctrl, "gimbal push attitude on;")
send_and_recv(sock_ctrl, "blaster bead 1;")

ui = UI(0)
block_skill = 0
is_blocked_man = False
is_blocked_data = False
is_blocked_blaster = True
blaster_flag_lock = threading.Lock()

# 线程1：接收数据
def thread1_func():
    global block_skill,is_blocked_blaster
    data1 = Data("game msg push [0, 6, 0, 0, 0, 12, 1, 65];")
    data0 = data1
    gb_data1 = GimbalData("gimbal push attitude 0 0;")
    gb_data0 = gb_data1
    while True: 
        # 接收信息推送端口
        buf, _ = sock_push.recvfrom(1024)
        buf = buf.decode('utf-8')
        data0 = data1
        gb_data0 = gb_data1
        if buf.startswith("game"):
            data1 = Data(buf)
            # 将数据转化为正负数
            data1.mouse_x = data1.mouse_x - 255 if data1.mouse_x > 125 else data1.mouse_x
            data1.mouse_y = data1.mouse_y - 255 if data1.mouse_y > 125 else data1.mouse_y
            # 均值滤波
            data1.mouse_x = (data1.mouse_x + data0.mouse_x) / 2
            data1.mouse_y = (data1.mouse_y + data0.mouse_y) / 2
            # #按键技能部分
            if 9 in data1.keys and 9 not in data0.keys:   #Z键    云台旋转180°
                block_skill = 1
            if 70 in data1.keys and 70 not in data0.keys:
                is_blocked_blaster = not is_blocked_blaster
                print("blaster: "+str(is_blocked_blaster))
            if 80 in data1.keys and 80 not in data0.keys:
                ui.is_setting = not ui.is_setting
        elif buf.startswith('gimbal'):
            gb_data1= GimbalData(buf)
            
        # 数据进入传输队列
        queue1.put(data1)
        queue1.put(gb_data1)

        while is_blocked_data == True:
            time.sleep(0.1)
# 线程2：阻塞技能
def thread2_func():
    while True:
        # 获取队列中的数据
        global block_skill,is_blocked_man,is_blocked_data
        if block_skill == 1:
            is_blocked_man = True
            is_blocked_data = True
            time.sleep(0.1)
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 450;")
            time.sleep(0.4)
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 0;")
            is_blocked_man = False
            is_blocked_data = False
            block_skill = 0
        time.sleep(0.1)
# 线程手动操作：阻塞技能
def thread3_func():
    global is_blocked_man
    loop_count = True  #初始化计数变量
    while True:
        # 获取队列中的数据
        data1=queue1.get()
        gb_data1=queue1.get()
        # 手动操作
        move_speed = 150  # 行走速度
        rush_speed = 500  # 疾跑速度
        speed_tr = move_speed  # 默认平移速度等于行走速度
        speed_th = 2.5  # 底盘跟随云台速度比例
        x, y, z = 0, 0, 0  # 底盘运动三维速度 
        tr_dir = 0  # 底盘坐标系的运动方向

        if 16 in data1.keys:  # shift键
            speed_tr = rush_speed
        else:
            speed_tr = move_speed

        if (87 in data1.keys):  # W键
            x = speed_tr
        elif (83 in data1.keys):  # S键
            x = -1 * speed_tr
        else:
            x = 0

        if (68 in data1.keys):  # D键
            y = speed_tr
        elif (65 in data1.keys):  # A键
            y = -1 * speed_tr
        else:
            y = 0

        # 将云台坐标系下运动方向转化为底盘坐标系下运动方向
        if y == 0:
            tr_dir = gb_data1.yaw
        elif x == 0:
            tr_dir = gb_data1.yaw + 90
        else:
            tr_dir = gb_data1.yaw + 45

        x *= math.cos(math.radians(tr_dir))  # 根据底盘坐标系运动方向计算X方向速度分量
        y *= math.sin(math.radians(tr_dir))  # 根据底盘坐标系运动方向计算Y方向速度分量
        z = gb_data1.yaw * speed_th  # 根据云台与底盘夹角比例控制Z轴

        if (loop_count == True):  # 两种命令间隔发送，在同一循环内发送会造成卡顿与延迟
            if ui.is_setting == False:
                send_and_recv(sock_ctrl, "gimbal speed p {0} y {1};".format(data1.mouse_y * 28, data1.mouse_x * 20))
        else:
            send_and_recv(sock_ctrl, "chassis wheel w1 {0} w2 {1} w3 {2} w4 {3};".format(x - y - z, x + y + z, x - y + z, x + y - z))
        
        # 循环技计数
        loop_count = not loop_count

        while is_blocked_man == True:
            time.sleep(0.1)
# 线程4：UI控制
def thread4_func():
    pass
# 线程5：定频发射
def thread5_func():
    global is_blocked_blaster
    while True:
        # 检查是否可以执行
        while is_blocked_blaster == False:
            send_and_recv(sock_ctrl, "blaster fire;")
            time.sleep(0.3)
        time.sleep(0.1)

# 创建队列
queue1 = Queue()    # 数据传输（thread1~thread2）
# 创建线程对象
thread1 = threading.Thread(target=thread1_func)
thread2 = threading.Thread(target=thread2_func)
thread3 = threading.Thread(target=thread3_func)
thread4 = threading.Thread(target=thread4_func)
thread5 = threading.Thread(target=thread5_func)    
# 启动线程
thread1.start()
thread2.start()
thread3.start()
# thread4.start()
thread5.start()