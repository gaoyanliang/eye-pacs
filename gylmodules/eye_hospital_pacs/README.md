眼科 HIS 数据库

192.168.190.254   zlhis/rshis   账号密码 ZLHIS/DAE42


## 定时将指定目录中的文件转移至 统一共享目录中

任务计划程序面板
按 Win + R 键打开“运行”对话框，然后输入 taskschd.msc 并按回车键，这将打开“任务计划程序”窗口。

在各个检查设备所在 windows 电脑上 按顺序执行如下步骤：

1. 用文本编辑器（推荐 VSCode 或记事本）新建一个文件，内容写好你的 `transfer.ps1` 脚本。
2. Windows 默认禁止运行脚本，需要设置允许脚本执行, 以管理员身份打开 PowerShell,  输入以下命令： Set-ExecutionPolicy RemoteSigned ,  出现提示，输入 `Y` 回车确认。
3. 测试脚本：打开普通 PowerShell（不用管理员）： .\transfer.ps1  如果脚本运行没有错误，就说明环境正常。
4. 给脚本加定时执行（推荐任务计划） 

Windows 自带的 wscript.exe 可以彻底隐藏控制台窗口。

步骤：
创建一个 VBS 脚本（如 E:\script\run_hidden.vbs），内容如下：

```shell
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -NoLogo -NonInteractive -ExecutionPolicy Bypass -File ""E:\script\transfer.ps1""", 0, False
```

0 表示 完全隐藏窗口（无闪烁）。
False 表示 不等待脚本执行完成（避免阻塞）。
修改计划任务命令，改为调用 VBS 脚本：
```shell
schtasks /create /tn "每分钟执行一次同步文件" /tr "wscript.exe ""E:\script\run_hidden.vbs""" /sc minute /mo 1
```

✅ 彻底无窗口，适用于所有 Windows 版本。


脚本内容如下：

```shell
# 定义本地监控文件夹路径
$sourceFolder = "C:\WatchFolder"

# 定义目标共享文件夹路径
$destFolder = "\\TARGET-PC\SharedFolder"

# 记录已转移文件的记录文件路径（防止重复转移）
$recordFile = "$PSScriptRoot\transfer_record.txt"

# 读取已处理文件列表
if (Test-Path $recordFile) {
    $processedFiles = Get-Content $recordFile
} else {
    $processedFiles = @()
}

# 获取当前文件夹中所有文件
$currentFiles = Get-ChildItem -Path $sourceFolder -File

foreach ($file in $currentFiles) {
    # 如果文件未被处理过
    if (-not $processedFiles.Contains($file.Name)) {
      try {
            # 获取当前时间戳
            $timestamp = Get-Date -Format "yyyyMMddHHmmss"
            
            # 构建新文件名（始终添加时间戳）
            $newName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name) + 
                      "_" + $timestamp + 
                      [System.IO.Path]::GetExtension($file.Name)
            
            $destPath = Join-Path -Path $destFolder -ChildPath $newName
            
            # 复制文件到目标共享文件夹
            Copy-Item -Path $file.FullName -Destination $destFolder -Force

            # 记录该文件名，避免重复处理
            Add-Content -Path $recordFile -Value $file.Name

            # 可选：复制成功后删除本地文件
            Remove-Item -Path $file.FullName -Force
        } catch {
            Write-Host "复制文件 $($file.Name) 失败： $_"
        }
    }
}
```

```shell
<#
.SYNOPSIS
监控本地文件夹并自动同步文件到共享目录，记录详细日志。 优化版-添加日志
#>

# 配置参数
$sourceFolder = "C:\WatchFolder"          # 本地监控文件夹
$destFolder = "\\TARGET-PC\SharedFolder"   # 目标共享文件夹
$recordFile = "$PSScriptRoot\transfer_record.txt"  # 已处理文件记录
$logFile = "$PSScriptRoot\transfer_log.txt"        # 日志文件路径
$deleteAfterCopy = $true                  # 复制后是否删除源文件

# 初始化日志函数
function Write-Log {
    param (
        [string]$Message,
        [string]$Level = "INFO"  # INFO/WARNING/ERROR
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    Add-Content -Path $logFile -Value $logEntry
    Write-Host $logEntry -ForegroundColor $(if ($Level -eq "ERROR") { "Red" } elseif ($Level -eq "WARNING") { "Yellow" } else { "White" })
}

# 检查必要目录是否存在
if (-not (Test-Path -Path $sourceFolder -PathType Container)) {
    Write-Log "本地监控文件夹不存在: $sourceFolder" -Level "ERROR"
    exit 1
}

if (-not (Test-Path -Path $destFolder -PathType Container)) {
    Write-Log "目标共享文件夹不可访问: $destFolder" -Level "ERROR"
    exit 1
}

# 初始化记录文件
if (-not (Test-Path $recordFile)) {
    New-Item -Path $recordFile -ItemType File -Force | Out-Null
    Write-Log "已创建新的记录文件: $recordFile"
}

# 读取已处理文件列表
try {
    $processedFiles = Get-Content $recordFile -ErrorAction Stop
} catch {
    Write-Log "读取记录文件失败: $_" -Level "ERROR"
    $processedFiles = @()
}

# 获取当前文件列表
try {
    $currentFiles = Get-ChildItem -Path $sourceFolder -File
    Write-Log "扫描到 $($currentFiles.Count) 个待处理文件"
} catch {
    Write-Log "获取文件列表失败: $_" -Level "ERROR"
    exit 1
}

# 处理文件
foreach ($file in $currentFiles) {
    if ($processedFiles -contains $file.Name) {
        Write-Log "跳过已处理文件: $($file.Name)"
        continue
    }

    try {
        # 复制文件
        $destPath = Join-Path -Path $destFolder -ChildPath $file.Name
        Copy-Item -Path $file.FullName -Destination $destPath -Force
        Write-Log "成功复制文件: $($file.Name) → $destFolder"

        # 记录到已处理列表
        Add-Content -Path $recordFile -Value $file.Name

        # 可选：删除源文件
        if ($deleteAfterCopy) {
            Remove-Item -Path $file.FullName -Force
            Write-Log "已删除源文件: $($file.FullName)"
        }
    } catch {
        Write-Log "处理文件 $($file.Name) 失败: $_" -Level "ERROR"
    }
}

Write-Log "文件同步完成"
```




## 服务器（ubuntu 24.04）上安装 samba 创建共享文件夹

1. Ubuntu（Debian系）

安装 Samba

sudo apt update
sudo apt install samba -y


配置共享目录

编辑配置文件：
sudo nano /etc/samba/smb.conf

添加示例配置（匿名可写共享）：
[shared]
   path = /srv/samba/shared      # 共享目录路径（需提前创建）
   browsable = yes               # 允许在网络邻居中可见
   writable = yes                # 允许写入
   guest ok = yes                # 允许匿名访问（生产环境建议设为 no）
   create mask = 0644            # 新建文件权限（宽松模式，建议改为 0644）
   directory mask = 0755         # 新建目录权限（建议改为 0755）


创建目录并设置权限

sudo mkdir -p /srv/samba/shared
sudo chmod -R 777 /srv/samba/shared  # 临时简化权限


重启服务

sudo systemctl restart smbd nmbd
sudo systemctl enable smbd nmbd  # 开机自启

3. 通用验证

Windows访问测试

在资源管理器地址栏输入：

\\linux_ip\shared

或通过PowerShell测试：
Test-NetConnection -ComputerName 192.168.1.100 -Port 445


Linux端调试

查看Samba日志：
sudo tail -f /var/log/samba/log.smbd


## 安装 conda & python 环境


在 Ubuntu 24.04 上安装 Conda、Python 环境及依赖的完整指南：

1. 安装 Miniconda（推荐轻量版）

# 下载最新Miniconda安装脚本（Linux x86_64）
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh

# 运行安装脚本（默认安装到~/miniconda3）
bash ~/miniconda.sh -b -p ~/miniconda3

# 初始化conda（将conda加入PATH）
~/miniconda3/bin/conda init bash
source ~/.bashrc  # 或重新打开终端

# 验证安装
conda --version

# 接受 main 通道的条款
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main

# 接受 r 通道的条款
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r


2. 创建Python虚拟环境

# 创建名为myenv的Python 3.10环境（可指定其他版本）
conda create -n myenv python=3.10 -y

# 激活环境
conda activate myenv

# 验证Python版本
python --version


3. 安装Python依赖

方式3：从requirements.txt安装

# 从本地 3.9环境导出 requirements.txt

.venv/bin/pip freeze > requirements.txt

# 安装所有依赖
pip install -r requirements.txt


4. 环境管理常用命令

# 列出所有环境
conda env list

# 导出环境配置
conda env export > environment.yml

# 从yml文件创建环境
conda env create -f environment.yml

# 删除环境
conda remove -n myenv --all

7. 验证安装

# 运行Python交互环境测试
python -c "import numpy, pandas, flask; print('All packages imported successfully')"


注意事项：

1. 建议为每个项目创建独立环境
2. 优先使用conda安装科学计算包（如numpy），避免ABI兼容问题
3. 生产环境建议使用pip freeze > requirements.txt精确锁定版本
4. Ubuntu 24.04默认Python版本为3.11，conda允许创建任意版本环境

卸载方法：

# 完全移除Miniconda
rm -rf ~/miniconda3
# 然后编辑~/.bashrc删除conda相关PATH


## 安装mysql

在 Ubuntu 24.04 上安装 MySQL 的步骤如下：

1. 更新系统包

sudo apt update
sudo apt upgrade -y


2. 安装 MySQL Server

sudo apt install mysql-server -y


3. 启动 MySQL 服务

sudo systemctl start mysql
sudo systemctl enable mysql


4. 运行安全配置脚本

sudo mysql_secure_installation

按照提示操作：
1. 设置 root 密码
2. 移除匿名用户（选 Y）
3. 禁止 root 远程登录（选 N）
4. 移除测试数据库（选 Y）
5. 重新加载权限表（选 Y）

5. 验证安装

sudo mysql -u root -p

输入密码后应该能看到 MySQL 提示符。

6. 常用命令

# 查看状态
sudo systemctl status mysql

# 重启服务
sudo systemctl restart mysql

# 停止服务
sudo systemctl stop mysql


7. 配置远程访问（可选）

如果需要远程访问 MySQL：
1. 编辑配置文件：
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf

找到 bind-address 并修改为：

bind-address = 0.0.0.0


2. 创建远程用户：
CREATE USER 'root'@'%' IDENTIFIED BY 'nsyy0601.';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%';
FLUSH PRIVILEGES;


3. 重启 MySQL：
sudo systemctl restart mysql


8. 防火墙设置（如有需要）

sudo ufw allow 3306


这样就完成了 MySQL 在 Ubuntu 24.04 上的安装和基本配置。

改用密码认证（生产环境必须）
sudo mysql -u root
在 MySQL 中执行：
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '你的密码';
FLUSH PRIVILEGES;



## 使用 Nginx 部署前端项目

在 Ubuntu 24.04 上部署 Vue 前端项目，可以通过 Nginx 或 PM2 实现。以下是详细步骤：

---

## **方法 1：使用 Nginx 部署（生产环境推荐）**
### **1. 安装 Node.js 和 npm**
Vue 项目需要 Node.js 环境：
```bash
# 使用 NodeSource 安装最新 LTS 版本
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs

# 验证安装
node -v  # 应输出 v18.x 或更高
npm -v
```

### **2. 安装依赖并构建 Vue 项目**
假设你的 Vue 项目代码在 `~/my-vue-project`：
```bash
cd ~/my-vue-project

# 安装依赖
npm install

# 构建生产环境代码（生成 dist 目录）
npm run build
```

### **3. 安装并配置 Nginx**
```bash
# 安装 Nginx
sudo apt install nginx

# 创建 Nginx 配置文件
sudo nano /etc/nginx/sites-available/my-vue-app
```
粘贴以下配置（替换 `your_domain.com` 为你的域名或服务器 IP）：
```nginx
server {
    listen 80;
    server_name your_domain.com;  # 改为你的域名或 IP

    root /var/www/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # 可选：静态文件缓存
    location /assets {
        expires 1y;
        add_header Cache-Control "public";
    }
}
```
启用配置并重启 Nginx：
```bash
sudo ln -s /etc/nginx/sites-available/my-vue-app /etc/nginx/sites-enabled
sudo nginx -t  # 测试配置语法
sudo systemctl restart nginx
```

### **4. 开放防火墙（如果启用）**
```bash
sudo ufw allow 'Nginx Full'  # 允许 HTTP/HTTPS
```

### **5. 访问项目**
- 通过浏览器访问 `http://your_domain.com` 或 `http://服务器IP`。

---

## **常见问题解决**
### **1. 路由 404 问题（Vue SPA）**
确保 Nginx 配置中包含：
```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

### **2. 静态资源加载失败**
检查 `dist` 目录权限：
```bash
sudo chown -R www-data:www-data /home/your_username/my-vue-project/dist
```

### **3. 端口冲突**
- 如果端口 80 被占用，修改 Nginx 的 `listen` 端口（如 `8080`）。
- 如果 3000 端口被占用，修改 PM2 的启动端口。

---

## **总结**
| 方法       | 适用场景                  | 优点                     |
|------------|--------------------------|--------------------------|
| **Nginx**  | 生产环境静态部署          | 高性能，支持 HTTPS/缓存  |
| **PM2**    | 开发或 SSR 项目           | 灵活，适合 Node.js 服务  |

根据需求选择合适的方式即可！



## 添加 NVIDIA 仓库

检查显卡版本
 nvidia-smi


sudo apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/3bf863cc.pub
sudo add-apt-repository "deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/ /"

# 安装 CUDA Toolkit 12.9
sudo apt install -y cuda-toolkit-12-9

# 验证安装
nvcc --version  # 应显示 CUDA 12.9



## 服务器 ubuntu24.04 设置固定id

https://blog.csdn.net/xiaochong0302/article/details/138975287




