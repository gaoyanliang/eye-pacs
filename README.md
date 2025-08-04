## 数据库账号

1. 本地数据库 Mysql 127.0.0.1:3306 root/gyl.2015
2. 服务器数据库 Mysql 192.168.3.12:3306 gyl/123456
3. 邮箱服务器 MariaDB 192.168.3.92:3306 root/NSYYnsyy@123 vmail
4. 新HIS数据库 PostgreSQL 192.168.8.57:6000 ogg/nyogg@2024 df_his       京颐移动护理系统  jk_jingyiydhl/jingyiydhl@123  df_his
5. 老HIS数据库 Oracle 192.168.3.8:1521 Service Name=ORCL zlhis/.1451534F81B 
6. OA服务器数据库 Mysql 192.168.3.12:3306 root/123123
7. PACS 数据库 SQL Server 192.168.3.53:1433 sa/NYS@intechhosun
8. 危机值数据库 Oracle 192.168.3.240:1521 Service Name=ORCL system/d67v7rbZyV

## 服务器账号

1. 192.168.3.240 gyl/gaoyanliang123     管理员  root/wy123qwe.
2. 192.168.3.12  gyl/gyl123      oa_test root/123456
3. 192.168.3.45  yifei/yifei
4. 192.168.3.92  cc/NSYYnsyy@123    邮箱服务器

 


## 医体融合项目 sport_mng

### 电子健康卡服务

电子健康卡服务分测试环境和正式环境，所有配置均在 `sport_mng/ehc_config.py` 中，其中通过 `isDebug` 配置来区分使用那个环境。

## 消息推送

android 使用的华为推送

iOS 使用的 apple APNs 推送，需要生成 推送证书（有效期一年，一年后需要重新生成）


创建推送证书
    选择 "Certificates" → "+" 创建新证书
    选择 "Apple Push Notification service SSL (Sandbox & Production)"
    选择对应的 App ID
    按照指示创建 CSR 文件（使用 Keychain Access）
    上传 CSR 文件并下载证书（.cer 文件）
    双击安装到钥匙串，然后导出为 .p12 文件（需要密码）

配置推送证书
    使用之前导出的 .p12 文件
    或者将证书转换为 PEM 格式：

```shell
openssl x509 -in aps.cer -inform der -out PushCert.pem
openssl pkcs12 -nocerts -out PushKey.pem -in 证书.p12 -legacy
cat PushCert.pem PushKey.pem > ck.pem

验证生成的 PEM 文件
openssl x509 -in ck.pem -text -noout  # 验证证书部分
openssl rsa -in ck.pem -check  # 验证私钥部分（如果有错误会提示）
```

发送测试推送

    可以使用命令行工具如 curl 或专用工具（如 Pusher、Postman）
    示例 cURL 命令（开发环境）：

```shell
curl -v \
-d '{"aps":{"alert":"Test push notification","sound":"default"}}' \
-H "apns-topic: YOUR_BUNDLE_ID" \
-H "apns-push-type: alert" \
-H "apns-priority: 10" \
--http2 \
--cert /path/to/cert.pem \
https://api.development.push.apple.com/3/device/DEVICE_TOKEN
```


生成不需要密码的证书

```shell
1. 先把所有证书文件备份一份到 /Users/gaoyanliang/nsyy/ios/配置推送证书/back

然后 

步骤 1：解密私钥（如果加密）（输入原始密码）
openssl rsa -in PushKey.pem -out PushKey_unencrypted.pem

步骤 2：重新合并文件
# 合并证书 + 无密码私钥
cat PushCert.pem PushKey_unencrypted.pem > ck1_fixed.pem

步骤 3：验证最终文件

# 检查证书
openssl x509 -in ck1_fixed.pem -noout -text

# 检查私钥
openssl rsa -in ck1_fixed.pem -check -noout

步骤 4：在代码中使用

from aioapns import APNs

apns = APNs(
    client_cert="ck1_fixed.pem",  # 使用修复后的文件
    use_sandbox=True,  # 开发环境=True，生产环境=False
)
```