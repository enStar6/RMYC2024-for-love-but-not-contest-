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

def chassis_follow_gimbal(keys, yaw):
    # 手动操作
    move_speed = 150  # 行走速度
    rush_speed = 500  # 疾跑速度
    speed_tr = move_speed  # 默认平移速度等于行走速度
    speed_th = 2.5  # 底盘跟随云台速度比例
    x, y, z = 0, 0, 0  # 底盘运动三维速度 
    tr_dir = 0  # 底盘坐标系的运动方向

    if 16 in keys:  # shift键
        speed_tr = rush_speed
    else:
        speed_tr = move_speed

    if (87 in keys):  # W键
        x = speed_tr
    elif (83 in keys):  # S键
        x = -1 * speed_tr
    else:
        x = 0

    if (68 in keys):  # D键
        y = speed_tr
    elif (65 in keys):  # A键
        y = -1 * speed_tr
    else:
        y = 0

    # 将云台坐标系下运动方向转化为底盘坐标系下运动方向
    if y == 0:
        tr_dir = yaw
    elif x == 0:
        tr_dir = yaw + 90
    else:
        tr_dir = yaw + 45

    x *= math.cos(math.radians(tr_dir))  # 根据底盘坐标系运动方向计算X方向速度分量
    y *= math.sin(math.radians(tr_dir))  # 根据底盘坐标系运动方向计算Y方向速度分量
    z = yaw * speed_th  # 根据云台与底盘夹角比例控制Z轴

    send_and_recv(sock_ctrl, "chassis wheel w1 {0} w2 {1} w3 {2} w4 {3};".format(x-y-z,x+y+z,x-y+z,x+y-z))

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

class AIData:
    def __init__(self, raw):
        # substr = raw[21:-1]   # 消息推送
        # data_str_list = substr.split(' ')
        # self.pitch = float(data_str_list[0])
        # self.yaw = float(data_str_list[1])
        self.raw = raw
    def print_data(self):
        print(f"raw:{self.raw}")

# 创建两个锁对象
lock = threading.Lock()
send_recv_lock = threading.Lock()
blaster_event = threading.Event()
blaster_event.set()

# 等待EP启动完成
# for i in range(20,0,-1):
#     print("open sdk in "+str(i)+" seconds...")
#     time.sleep(1)

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
is_blocked_man_drive_chassis = False
is_blocked_man_drive_gimbal = False
is_blocked_blaster = True

# 线程1：接收数据、手动控制
def thread1_func():
    global block_skill  # 要执行的阻塞程序（技能）
    global is_blocked_blaster   # 是否禁止发射
    global is_blocked_man_drive_chassis   # 是否禁止手操底盘
    global is_blocked_man_drive_gimbal   # 是否禁止手操云台
    # 初始化4个数据对象
    data1 = Data("game msg push [0, 6, 0, 0, 0, 12, 0];")
    data0 = data1
    gb_data1 = GimbalData("gimbal push attitude 0 0;")
    gb_data0 = gb_data1
    lost_msg_count = 0    # 统计没收到信息的次数
    lost_flag = False   # 防止不断给is_blocked_man_drive_chassis和is_blocked_man_drive_gimbal归零
    while True: 
        # 接收信息推送端口
        buf, _ = sock_push.recvfrom(1024)
        buf = buf.decode('utf-8')
        # 循环内重申两个上一帧数据对象
        data0 = data1
        gb_data0 = gb_data1
        # 解析接收到的数据
        if buf.startswith("game"):  # 如果接收到的是键值数据
            lost_msg_count = 0
            data1 = Data(buf)
            # 将鼠标移动加速度数据转化为正负数
            data1.mouse_x = data1.mouse_x - 255 if data1.mouse_x > 125 else data1.mouse_x
            data1.mouse_y = data1.mouse_y - 255 if data1.mouse_y > 125 else data1.mouse_y
            # 均值滤波
            data1.mouse_x = (data1.mouse_x + data0.mouse_x) / 2
            data1.mouse_y = (data1.mouse_y + data0.mouse_y) / 2
            # 打印键值数据
            data1.print_data()
            # 按键技能部分
            if 9 in data1.keys and 9 not in data0.keys:   #TAB键    云台旋转180°
                block_skill = 1
            if 70 in data1.keys and 70 not in data0.keys:
                block_skill = 2 if not block_skill == 2 else 0
            # if data1.mouse_press == 2 and not data0.mouse_press == 2:   # 单点
            #     send_and_recv(sock_ctrl, "blaster fire;")
            # 鼠标控制云台运动
            if is_blocked_man_drive_gimbal == False:
                send_and_recv(sock_ctrl, "gimbal speed p {0} y {1};".format(data1.mouse_y * 22, data1.mouse_x * 16))
        elif buf.startswith('gimbal'):  # 如果接收到的是云台姿态数据
            gb_data1= GimbalData(buf)
            # 打印云台姿态数据
            gb_data1.print_data()
            # 键盘控制底盘及底盘跟随云台
            if is_blocked_man_drive_chassis == False:
                chassis_follow_gimbal(data1.keys, gb_data1.yaw)
        # 每次循环都递增，若收到键值信息会归零
        lost_msg_count += 1 if lost_msg_count < 30 else 0
        # 若连续3次未收到键值信息，则锁定云台、底盘的手操
        if lost_msg_count > 3:
            is_blocked_man_drive_chassis, is_blocked_man_drive_gimbal = True, True
            lost_flag = True
        elif lost_flag == True:     # 若收到键值信息且lost_flag为True（已经锁定底盘、云台），则解锁，重置lost_flag
            is_blocked_man_drive_chassis, is_blocked_man_drive_gimbal = False, False
            lost_flag = False
        if lost_msg_count > 3:     # 若连续三次未收到键值信息，则停止云台、底盘运动
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 0;")
            send_and_recv(sock_ctrl, "chassis wheel w1 0 w2 0 w3 0 w4 0;")
# 线程2：阻塞技能
def thread2_func():
    while True:
        # 获取队列中的数据
        global block_skill
        global is_blocked_man_drive_chassis
        global is_blocked_man_drive_gimbal
        global is_blocked_blaster
        if block_skill == 1:    # 暴风赤红经典转身
            is_blocked_man_drive_gimbal = True
            time.sleep(0.1)
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 450;")
            time.sleep(0.4)
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 0;")
            is_blocked_man_drive_gimbal = False
            block_skill = 0
        if block_skill == 2:    # 0.3秒发射
            while(block_skill == 2):
                send_and_recv(sock_ctrl, "blaster fire;")
                time.sleep(0.3)

        time.sleep(0.1)
# 线程3：UI控制
def thread3_func():
    pass

# 创建线程对象
thread1 = threading.Thread(target=thread1_func)
thread2 = threading.Thread(target=thread2_func)
thread3 = threading.Thread(target=thread3_func)    
# 启动线程
thread1.start()
thread2.start()
# thread3.start()

