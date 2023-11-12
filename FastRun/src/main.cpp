#include <Arduino.h>

//Serial2 Tx:17 Rx:16
//chassis speed x 1 y 0 z 0;  x前后y左右z转圈

int count;

void rush_out(){
  Serial2.print("chassis speed x 1 y 0 z 0;");vTaskDelay(500);
  Serial2.print("chassis speed x 0 y 0 z 180;");vTaskDelay(300);
  Serial2.print("chassis speed x 2 y 0 z 0;");vTaskDelay(700);
  Serial2.print("chassis speed x 0 y 1 z 0;");vTaskDelay(600);
  Serial2.print("chassis speed x 1 y 0 z 0;");vTaskDelay(500);
  Serial2.print("chassis speed x 0 y 0 z -180;");vTaskDelay(550);
  Serial2.print("chassis speed x 0 y 0 z 0;");vTaskDelay(200);
  
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200);
  delay(1000);
  Serial.println("wait 15 seconds...");
  delay(15000); //等待EP启动完成
  Serial.println("join in SDK...");
  Serial2.print("command;");delay(200); //进入SDK模式
  Serial2.print("game_msg on;");delay(1000);  //打开键值推送，但是只有操作手在赛事引擎也打开SDK模式才有推送信息
  while(Serial2.available()){ //清空串口缓冲区
    char s = Serial2.read();
  }
  while(!Serial2.available()){} //重复检测串口缓冲区是否有键值信息（检测操作手是否打开SDK模式）
}

void loop() {
  if(Serial2.available()){  //若串口有信息，则说明还没自检，count不断归零
    count=0;
    Serial.println(Serial2.readStringUntil('\n'));
  }else{  //若未收到信息，count不断递增
    count++;
    Serial.println(count);
  }
  if(count>=50){  //当count大于某个值（其实10就够了，这里保险给大一点）则说明长时间未收到信息（自检阶段开始，此时操作手可以将赛事引擎改成APP模式）
    Serial2.print("game_msg off;");delay(18000); //等待自检和倒数完成（事实上应抢跑1到2秒，自行按实际调整）
    rush_out(); //到位路线（自己按实际调整）
    Serial2.print("quit;"); //退出SDK模式，以便执行普通程序
    while(1){}  //锁死程序，除非手动还要用SDK
  }
  delay(10);
}
