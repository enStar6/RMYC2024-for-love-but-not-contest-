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

def send_and_recv(s, string, en_print=False):
    with send_recv_lock:
        s.send(string.encode('utf-8'))
        if en_print == True:
            print("send: " + string)
        buf = s.recv(1024)
        if en_print == True:
            print("back: " + buf.decode('utf-8'))
    return buf

def keep_still():
    send_and_recv(sock_ctrl, "gimbal speed p 0 y 0;")
    send_and_recv(sock_ctrl, "chassis wheel w1 0 w2 0 w3 0 w4 0;")

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

def sort_key(sublist):
    return sublist[0]

def power(mk1,std_pitch,std_yaw,block_skill):
    calc = [[lambda a,b,c,d,f:[b,f,c,f,d]if(b[0]+c[0]+d[0]==24)else[],
            lambda a,b,c,d,f:[a,f,b,f,c,f,d]if(a[0]+b[0]+c[0]+d[0]==24)else[],
            lambda a,b,c,d,f:[a,b,c,f,d]if(b[0]*10+c[0]+d[0]==24)else[],
            lambda a,b,c,d,f:[a,b,f,c,f,d]if(a[0]*10+b[0]+c[0]+d[0]==24)else[],
            lambda a,b,c,d,f:[a,b,f,c,d]if(a[0]*10+b[0]+c[0]*10+d[0]==24)else[]],
    
            [lambda a,b,c,d,f:[b,c,f,d]if(b[0]*10+c[0]-d[0]==24)else[],
            lambda a,b,c,d,f:[a,b,f,c,d]if(a[0]*10+b[0]-c[0]*10-d[0]==24)else[],
            lambda a,b,c,d,f:[a,b,f,c,f,d]if(a[0]*10+b[0]-c[0]-d[0]==24)else[]],
    
            [lambda a,b,c,d,f:[b,c,f,d]if((b[0]*10+c[0])/d[0]==24)else[],
            lambda a,b,c,d,f:[a,b,c,f,d]if((a[0]*100+b[0]*10+c[0])/d[0]==24)else[]],
            
            [lambda a,b,c,d,f:[c,f,d]if(c[0]*d[0]==24)else[],
            lambda a,b,c,d,f:[b,c,f,d]if(b[0]*10*c[0]*d[0]==24)else[],
            lambda a,b,c,d,f:[b,f,c,f,d]if(b[0]*c[0]*d[0]==24)else[],
            lambda a,b,c,d,f:[a,f,b,f,c,f,d]if(a[0]*b[0]*c[0]*d[0]==24)else[]]]
    
    order = [[0, 1, 2, 3], [0, 1, 3, 2], [0, 2, 1, 3], [0, 2, 3, 1],
             [0, 3, 1, 2], [0, 3, 2, 1], [1, 0, 2, 3], [1, 0, 3, 2],
             [1, 2, 0, 3], [1, 2, 3, 0], [1, 3, 0, 2], [1, 3, 2, 0],
             [2, 0, 1, 3], [2, 0, 3, 1], [2, 1, 0, 3], [2, 1, 3, 0],
             [2, 3, 0, 1], [2, 3, 1, 0], [3, 0, 1, 2], [3, 0, 2, 1],
             [3, 1, 0, 2], [3, 1, 2, 0], [3, 2, 0, 1], [3, 2, 1, 0]]      
    flag = 0
    for [a,b,c,d] in order:
        if flag == 1:break
        try:
            for func in calc[mk1[4][0]%10]:
                if flag == 1:break
                for target in func(mk1[a],mk1[b],mk1[c],mk1[d],mk1[4]):
                    if block_skill == 0:
                        flag = 1
                        break
                    if target != []:
                        flag = 1
                        target_pitch=target[2]-target[3]+math.atan((1-2*target[2])*math.tan(32/180*math.pi))*180/math.pi
                        target_yaw=math.atan((2*target[1]-1)*math.tan(45/180*math.pi))*180/math.pi
                        send_and_recv(sock_ctrl, "gimbal moveto p "+str(target_pitch+std_pitch)+" y "+str(target_yaw+std_yaw)+" vp 540 vy 540;",True)
                        time.sleep(0.08)
                        send_and_recv(sock_ctrl, "blaster fire;")
                        time.sleep(0.06)
        except:
            print("list index out of range !!!")

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
        output = "["+str(time.time())+"] "
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
        print(f"[{time.time()}] pitch:{self.pitch}° yaw:{self.yaw}°")

class UI:
    def __init__(self,mode):
        self.mode = mode
        self.is_setting = False

class AIData:
    def __init__(self, raw):
        self.raw = raw
        self.num = 0
        self.marker_list = []
        substr = raw[15:-1]
        data_str_list = substr.split(' ')
        if len(data_str_list) > 1:
            float_list = [float(x) for x in data_str_list]
            self.num = int(float_list[0])
            for i in range(self.num):
                new_marker = [int(float_list[i * 5 + 1]),
                                float(float_list[i * 5 + 2]),
                                float(float_list[i * 5 + 3]),
                                float(float_list[i * 5 + 4]),
                                float(float_list[i * 5 + 5])]
                new_marker[0] = 15 if new_marker[0] == 38 else new_marker[0]
                self.marker_list.append(new_marker)
            self.marker_list = sorted(self.marker_list, key=sort_key)
            try:
                for i in range(4):
                    self.marker_list[i][0] -= 10
            except:
                pass
    def print_marker(self):
        print("["+str(time.time())+"] "+str(self.marker_list))

class PID:
    def __init__(self, kp, ki, kd, maxIntergral, maxOutput, deadZone, errLpfRatio):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral = 0
        self.error = 0
        self.last_error = self.error
        self.output = 0
        self.maxIntergral = maxIntergral
        self.maxOutput = maxOutput
        self.deadZone = deadZone
        self.errLpfRatio = errLpfRatio
    def update(self, error):
        self.last_error = self.error
        self.error = error*self.errLpfRatio+self.last_error*(1-self.errLpfRatio)
        self.integral += self.error
        if self.integral > self.maxIntergral:
            self.integral = self.maxIntergral
        elif self.integral < -self.maxIntergral:
            self.integral = -self.maxIntergral
        derivative = (error - self.last_error)
        self.output = self.kp * error + self.ki * self.integral + self.kd * derivative
        if self.output > self.maxOutput:
            self.output = self.maxOutput
        elif self.output < -self.maxOutput:
            self.output = -self.maxOutput
        return self.output

# 创建两个锁对象
lock = threading.Lock()
send_recv_lock = threading.Lock()

# 全局定义
mk_list = []
block_skill = 0
std_pitch = 0
std_yaw = 0
is_blocked_blaster = False
is_blocked_man_drive_chassis = False
is_blocked_man_drive_gimbal = False

# 等待EP启动完成
# for i in range(20,0,-1):
#     print("open sdk in "+str(i)+" seconds...")
#     time.sleep(1)

# 与机器人控制命令端口建立 TCP 连接 （用于发送控制命令）
sock_ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print("Connecting sock_ctrl...")
sock_ctrl.connect(address_ctrl)
print("Connected!")

# 与机器人消息推送端口建立 UDP 连接 （用于接收推送信息）
sock_push = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print("Connecting sock_push...")
sock_push.bind(address_push)
print("Connected!")

# 线程1：接收数据、手动控制
def thread1_func():
    global mk_list
    global block_skill
    global std_pitch
    global std_yaw
    global is_blocked_blaster
    global is_blocked_man_drive_chassis
    global is_blocked_man_drive_gimbal
    # 初始化6个数据对象
    data1 = Data("game msg push [0, 6, 0, 0, 0, 12, 0];")
    data0 = data1
    gb_data1 = GimbalData("gimbal push attitude 0 0;")
    gb_data0 = gb_data1
    ai_data1 = AIData("")
    ai_data0 = ai_data1
    #初始化PID
    basePidPitch = PID(400,5,3, 540,540, 0.03,1)
    basePidYaw   = PID(500,5,3, 540,540, 0.03,1)
    lost_msg_count = 0    # 统计未收到信息的次数
    while True: 
        # 接收信息推送端口
        buf, _ = sock_push.recvfrom(1024)
        buf = buf.decode('utf-8')
        # print("buf:"+buf)
        # 循环内重申两个上一帧数据对象
        data0 = data1
        gb_data0 = gb_data1
        ai_data0 = ai_data1
        proYaw = 0
        proPitch = 0
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
            if 70 in data1.keys and 70 not in data0.keys:   #F键    每隔0.3秒射一次
                block_skill = 2 if not block_skill == 2 else 0
            if 71 in data1.keys and 71 not in data0.keys:     #E键    能量机关
                block_skill = 3 if not block_skill == 3 else 0
            if data1.mouse_press == 1:
                print("mouse right")
                if len(ai_data1.marker_list) >= 1:
                    for mark in ai_data1.marker_list:
                        if mark[0]==27:
                            proYaw = basePidYaw.update(mark[1]-0.5)
                            proPitch = basePidPitch.update(0.5-mark[2])
                            print("proYaw:",proYaw,"proPitch:",proPitch)
                            break
            else:
                proPitch = 0
                proYaw = 0
            # 鼠标控制云台运动
            if is_blocked_man_drive_gimbal == False:
                send_and_recv(sock_ctrl, "gimbal speed p {0} y {1};".format(data1.mouse_y * 22 + int(proPitch), data1.mouse_x * 16 + int(proYaw)))
        elif buf.startswith('gimbal'):  # 如果接收到的是云台姿态数据
            gb_data1= GimbalData(buf)
            std_pitch,std_yaw = gb_data1.pitch,gb_data1.yaw
            # 打印云台姿态数据
            gb_data1.print_data()
            # 键盘控制底盘及底盘跟随云台
            if is_blocked_man_drive_chassis == False:
                chassis_follow_gimbal(data1.keys, gb_data1.yaw)
        elif buf.startswith('AI push'):  # 如果接收到的是视觉标签数据
            ai_data1 = AIData(buf)
            ai_data1.print_marker()
            mk_list = ai_data1.marker_list
        # # 每次循环都递增，若收到键值信息会归零
        # lost_msg_count += 1 if lost_msg_count < 30 else 0
        # # 若连续3次未收到键值信息，则锁定云台、底盘的手操
        # if lost_msg_count > 3:
        #     is_blocked_man_drive_chassis = True   #锁定底盘手动遥控
        #     is_blocked_man_drive_gimbal = True    #锁定云台手动遥控
        #     keep_still()
        # elif lost_msg_count < 3:     # 若收到键值信息且lost_flag为True（已经锁定底盘、云台），则解锁，重置lost_flag
        #     is_blocked_man_drive_chassis = False   #锁定底盘手动遥控
        #     is_blocked_man_drive_gimbal = False    #锁定云台手动遥控
# 线程2：阻塞技能
def thread2_func():
    while True:
        # 获取队列中的数据
        global mk_list
        global block_skill
        global std_pitch
        global std_yaw
        global is_blocked_man_drive_chassis
        global is_blocked_man_drive_gimbal
        global is_blocked_blaster
        if block_skill == 1:    # 暴风赤红经典转身
            is_blocked_man_drive_gimbal = True
            # time.sleep(0.1)
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 450;")
            time.sleep(0.4)
            send_and_recv(sock_ctrl, "gimbal speed p 0 y 0;")
            is_blocked_man_drive_gimbal = False
            block_skill = 0
        if block_skill == 2:    # 每隔0.3秒发射一次
            while(block_skill == 2):
                send_and_recv(sock_ctrl, "blaster fire;")
                time.sleep(0.3)
        if block_skill == 3:    # 能量机关
            is_blocked_man_drive_chassis = True   #锁定底盘手动遥控
            is_blocked_man_drive_gimbal = True    #锁定云台手动遥控
            keep_still()    # 保持底盘、云台静止
            while(block_skill == 3):
                if len(mk_list) >= 5:   #识别到符合要求的标签
                    send_and_recv(sock_ctrl, "gimbal moveto p 0 y 0 vp 180 vy 180;",True)
                    time.sleep(0.3)
                    power(mk_list,0,0,block_skill)    #核心算法和击打操作
                    send_and_recv(sock_ctrl, "gimbal moveto y 0 vy 540;",True)
                    is_blocked_man_drive_chassis = False   #解锁底盘手动遥控
                    is_blocked_man_drive_gimbal = False    #解锁云台手动遥控
                    block_skill = 0     # 复位技能标识变量
                    break
                time.sleep(0.1)     #必须加，不然多线程处理不过来
            is_blocked_man_drive_chassis = False   #锁定底盘手动遥控
            is_blocked_man_drive_gimbal = False    #锁定云台手动遥控
        time.sleep(0.1)     #必须加，不然多线程处理不过来
# 线程3：UI控制
def thread3_func():
    pass

# 发送初始化控制命令给机器人
send_and_recv(sock_ctrl, "command;")    #进入sdk模式
send_and_recv(sock_ctrl, "quit;")       #退出sdk模式
send_and_recv(sock_ctrl, "command;")    #sdk再重进是为了解决图传被卡住的bug（DJI的锅）
send_and_recv(sock_ctrl, "robot mode free;")
send_and_recv(sock_ctrl, "game_msg on;")    #打开键值推送
send_and_recv(sock_ctrl, "blaster bead 1;")     #设置单次发射数量

def main():
    send_and_recv(sock_ctrl, "AI push marker on;",True)  #打开视觉标签推送
    send_and_recv(sock_ctrl, "gimbal push attitude on;")    #打开云台姿态信息推送

    # 创建线程对象
    thread1 = threading.Thread(target=thread1_func)
    thread2 = threading.Thread(target=thread2_func)
    thread3 = threading.Thread(target=thread3_func)    
    # 启动线程
    thread1.start()
    thread2.start()
    # thread3.start()

    # 等待所有线程完成
    thread1.join()
    thread2.join()
    # thread3.join()

while True:
    try:
        main()
    except Exception as e:
        print(f"Caught exception: {e}")
