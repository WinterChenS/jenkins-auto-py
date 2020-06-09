#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask
from flask import request
from flask import jsonify
from flask import Response

import requests
import subprocess
import json
import socket
import datetime
import time

app = Flask(__name__)

@app.route('/shell', methods=['POST'])
def processTask():
    print('开始处理部署任务')
    shellRequestJson = request.get_json()
    print('==================[ 入参 ]==================')
    print(shellRequestJson)
    print('==================[ 入参 ]==================')
    imageName = shellRequestJson.get('imageName')
    if imageName is None:
        return jsonify(code=400, data='', msg='imageName 不能为空') 
    tag = shellRequestJson.get('tag')
    if tag is None:
        return jsonify(code=400, data='', msg='tag 不能为空') 
    simpleImageName = shellRequestJson.get('simpleImageName')
    if simpleImageName is None:
        return jsonify(code=400, data='', msg='simpleImageName 不能为空') 
    port = shellRequestJson.get('port')
    if port is None:
        return jsonify(code=400, data='', msg='port 不能为空') 
    envs = shellRequestJson.get('envs')
    volumes = shellRequestJson.get('volumes')
    reg_url = shellRequestJson.get('registerServiceInfo').get('registerCenterUrl')
    if reg_url is None:
        return jsonify(code=400, data='', msg='registerCenterUrl 不能为空') 
    reg_service_name = shellRequestJson.get('registerServiceInfo').get('serviceName')
    if reg_service_name is None:
        return jsonify(code=400, data='', msg='serviceName 不能为空') 
    reg_port = shellRequestJson.get('registerServiceInfo').get('port')
    ip = getCurrentIp()
    params = {'serviceName':reg_service_name,'ip':ip, 'port':reg_port}
    try:
        cancelServiceFromRegisterCenter(reg_url, params)
        executeShell(imageName, tag, simpleImageName, port, envs, volumes)
        #不使用下面方式：因为jenkins请求1分钟就会超时，所以改成在jenkins端检查服务健康
        #eachUnitHealth(ip, reg_port, reg_context_path, reg_delay_seconds)
    except Exception as e:
        print('部署任务失败，系统异常' + str(e))
        return jsonify(code=500, data='', msg='部署失败，系统异常')
    print('处理部署任务结束')
    return jsonify(code=200, data='', msg='success')

@app.route('/health', methods=['POST'])    
def checkServiceHealth():
    print('开始检查服务健康度')
    servicePort = request.get_json().get('port')
    context_path = request.get_json().get('context_path')
    health_path = request.get_json().get('health_path')
    print('==================[ 入参 ]==================')
    print(request.get_json())
    print('==================[ 入参 ]==================')
    result = checkHealth(getCurrentIp(),servicePort,context_path,health_path)
    if result == True:
        return jsonify(code=200, data='', msg='success')
    else:
        return jsonify(code=500, data='', msg='unhealth')

def cancelServiceFromRegisterCenter(url, params):
    print('开始注销服务')
    lt = []
    for k,v in params.items():
        lt.append(k+'='+str(v))
    queryStr = '&'.join(lt)
    res = requests.delete(url + '?' + queryStr)
    print('注销服务的结果: ' + res.text)
    if res.ok:
        print('注销服务成功')
        return True
    else:
        print('注销服务失败')
        return False

def executeShell(imageName, tag, simpleImageName, port, envs, volumes):
    print('=======================[ 执行部署容器的命令开始 ]=======================')
    # 服务注销之后需要延迟一定的时间，等待请求处理完成
    time.sleep(3)
    # stop old container
    stopContainer(simpleImageName)
    # rmove old container
    removeContainer(simpleImageName)
    # remove old image
    removeImage(imageName)
    # pull new image
    pullImage(imageName, tag)
    # run new image
    runImage(port, simpleImageName, imageName, tag, envs, volumes)
    print('=======================[ 执行部署容器的命令结束 ]=======================')
    return True

def stopContainer(simpleImageName):
    print('>>> 停止容器开始')
    command = 'docker stop ' + simpleImageName
    print('现在执行命令：' + command)
    subprocess.run(command, shell=True)
    print('<<< 停止容器的完成')
    
    return True

def removeContainer(simpleImageName):
    print('>>> 开始删除容器')
    command = 'docker rm ' + simpleImageName
    print('现在执行命令：' + command)
    subprocess.run(command, shell=True)
    print('<<< 删除容器的完成')
    
    return True

def removeImage(imageName):
    print('>>> 开始删除镜像')
    command = 'docker rmi -f ' + imageName
    print('现在执行命令：' + command)
    subprocess.run(command, shell=True)
    print('<<< 删除镜像的完成')
    
    return True

def pullImage(imageName, imageTag):
    print('>>> 开始拉取镜像')
    command = 'docker pull ' + imageName + ':' + imageTag
    print('现在执行命令：' + command)
    subprocess.run(command, shell=True)
    print('<<< 拉取镜像的完成')
    
    return True

def runImage(port, simpleImageName, imageName, imageTag, envCommands, volumesArgs):
    print('>>> 开始运行容器')
    command = 'docker run -p ' + str(port) + ':' + str(port)
    command += ' --network=host --name=' + str(simpleImageName) + ' -d '
    if not envCommands is None:
        command += envCommands + ' '
    if not volumesArgs is None:
        command += volumesArgs + ' '
    command += imageName + ':' + imageTag
    print('现在执行命令：' + command)
    subprocess.run(command, shell=True)
    print('<<< 运行容器完成')
    
    return True

# 暂时不用
def eachUnitHealth(serverIp, port, reg_context_path, delaySeconds):
    print('=======================[ 服务健康监测 ]=======================')
    delaySeconds = int(delaySeconds)
    if delaySeconds > 0:
        time.sleep(delaySeconds)
    flag = False

    maxRetryCount = 20
    
    retryCount = 0
    while flag == False:
        flag = checkHealth(serverIp, port, reg_context_path, None)
        if flag == True:
            print('=======================[ 服务启动成功 ]=======================')
            return True
        time.sleep(5)
        retryCount += 1
        if retryCount >= maxRetryCount:
            print('=======================[ 服务启动失败 ]=======================')
            return False
        
def checkHealth(host, port, reg_context_path, reg_health_path):
    print('=======================[ 正在检查服务是否启动完成 ]=======================')
    time.sleep(10)
    url = 'http://' + host + ':' + str(port)
    if not reg_context_path is None:
        url += reg_context_path
    if reg_health_path is None:
        url += '/markting-framework/touch'
    else:
        url += reg_health_path
    print('监测服务地址：')
    print(url)
    try:
        res = requests.get(url)
        print(res)
        if res.ok:
            return True

    except Exception as e:
        print('服务未提供服务')
        return False
    return False

def getCurrentIp():
    try:
        s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(('10.0.0.1',8080))
        ip= s.getsockname()[0]
    finally:
        s.close()
    print("当前服务器IP地址:")
    print(ip)
    return ip

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8008)