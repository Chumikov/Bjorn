## 🔧 Установка и настройка

<p align="center">
  <img src="https://github.com/user-attachments/assets/c5eb4cc1-0c3d-497d-9422-1614651a84ab" alt="thumbnail_IMG_0546" width="98">
</p>

## 📚 Содержание

- [Предварительные требования](#-предварительные-требования)
- [Быстрая установка](#-быстрая-установка)
- [Ручная установка](#-ручная-установка)
- [Лицензия](#-лицензия)

Используйте Raspberry Pi Imager для установки ОС:
https://www.raspberrypi.com/software/

### 📌 Предварительные требования для RPI zero W (32-бит)
![image](https://github.com/user-attachments/assets/3980ec5f-a8fc-4848-ab25-4356e0529639)

- Установленная Raspberry Pi OS.
    - Стабильная:
      - Система: 32-бит
      - Версия ядра: 6.12
      - Версия Debian: 12 (bookworm) '2026-04-13-raspios-bookworm-armhf-lite'
- Имя пользователя и hostname установлены в `bjorn`.
- e-Paper HAT 2.13 дюйма подключён к GPIO-пинам.

### 📌 Предварительные требования для RPI zero W2 (64-бит)

![image](https://github.com/user-attachments/assets/e8d276be-4cb2-474d-a74d-b5b6704d22f5)

Проект не разрабатывался специально для Raspberry Pi Zero W2 64-бит, но несколько отзывов подтвердили, что установка работает корректно.

- Установленная Raspberry Pi OS.
    - Стабильная:
      - Система: 64-бит
      - Версия ядра: 6.12
      - Версия Debian: 12 (bookworm) '2026-04-13-raspios-bookworm-arm64-lite'
- Имя пользователя и hostname установлены в `bjorn`.
- e-Paper HAT 2.13 дюйма подключён к GPIO-пинам.

### 📌 Предварительные требования для RPi 5 (64-бит, BCM2712)

- Установленная Raspberry Pi OS (Legacy, 64-bit).
    - Система: 64-bit (ARM64/aarch64; 32-bit не поддерживается на BCM2712)
    - Версия ядра: 6.12
    - Версия Debian: 12 (bookworm) '2026-04-13-raspios-bookworm-arm64-lite'
- Имя пользователя и hostname установлены в `bjorn`.
- e-Paper HAT 2.13 дюйма подключён к GPIO-пинам.
- **Минимальная версия Bjorn**: v1.3.1+ (мульти-источник platform detection для BCM2712). Рекомендуется v1.3.4+.



На данный момент протестированы и поддерживаются экраны v2 и v4.
Надеемся, что V1 и V3 также будут работать корректно.

### ⚡ Быстрая установка

Самый быстрый способ установить Bjorn — использовать скрипт автоматической установки:

```bash
# Скачать и запустить установщик
wget https://raw.githubusercontent.com/Chumikov/Bjorn/refs/heads/main/install_bjorn.sh
sudo chmod +x install_bjorn.sh
sudo ./install_bjorn.sh
# Выберите вариант 1 для автоматической установки. Это может занять некоторое время, так как будет установлено множество пакетов и модулей. Необходимо выполнить перезагрузку по завершении.
```

### 🧰 Ручная установка

#### Шаг 1: Активация SPI и I2C

```bash
sudo raspi-config
```

- Перейдите в **"Interface Options"**.
- Включите **SPI**.
- Включите **I2C**.

#### Шаг 2: Системные зависимости

```bash
# Обновление системы
sudo apt-get update && sudo apt-get upgrade -y

# Установка необходимых пакетов

 sudo apt install -y \
  libjpeg-dev \
  zlib1g-dev \
  libpng-dev \
  python3-dev \
  libffi-dev \
  libssl-dev \
  libgpiod-dev \
  libi2c-dev \
  build-essential \
  python3-pip \
  wget \
  lsof \
  git \
  libopenjp2-7 \
  nmap \
  libopenblas-dev \
  bluez-tools \
  bluez \
   dhcpcd5 \
   bridge-utils \
   python3-pil \
   smbclient \
   wireless-tools


# Обновление базы скриптов Nmap

sudo nmap --script-updatedb

```

#### Шаг 3: Установка Bjorn

```bash
# Клонирование репозитория Bjorn
cd /home/bjorn
git clone https://github.com/Chumikov/Bjorn.git
cd Bjorn

# Установка Python-зависимостей
sudo pip install -r requirements.txt --break-system-packages
# Поскольку пока не удалось получить стабильную установку в виртуальном окружении, зависимости установлены системно (с --break-system-packages). На данный момент это не вызывало проблем. Вы можете попробовать установить их в виртуальном окружении, если хотите.
```

##### 3.1: Настройка типа e-Paper дисплея
Выберите версию вашего e-Paper HAT, изменив файл конфигурации:

1. Откройте файл конфигурации:
```bash
sudo vi /home/bjorn/Bjorn/config/shared_config.json
```
Нажмите `i` для входа в режим вставки
Найдите строку, содержащую `"epd_type"`:
Измените значение в соответствии с моделью вашего экрана:

- Для 2.13 V1: `"epd_type": "epd2in13"`,
- Для 2.13 V2: `"epd_type": "epd2in13_V2"`,
- Для 2.13 V3: `"epd_type": "epd2in13_V3"`,
- Для 2.13 V4: `"epd_type": "epd2in13_V4"`,

Нажмите `Esc` для выхода из режима вставки
Введите `:wq` и нажмите `Enter` для сохранения и выхода

##### 3.2: Веб-аутентификация (страница логина)

Начиная с v1.4.0 вход в веб-интерфейс (`http://[ip]:8000`) — через
**страницу логина** `/login` с сессионными cookie. Учётные данные по
умолчанию (сменим пароль перед выставлением в сеть):

- **Логин:** `admin`
- **Пароль:** `bjorn`

При первом входе plaintext-пароль автоматически мигрируется в salted+hash
(PBKDF2-SHA256). Чтобы сменить пароль или отключить аутентификацию,
отредактируйте `/home/bjorn/Bjorn/config/shared_config.json`:

```json
"web_auth_enabled": true,
"web_username": "admin",
"web_password": "свой-надёжный-пароль",
"web_bind_address": "0.0.0.0"
```

(после следующего входа `web_password` заменится на `web_password_hash` +
`web_password_salt`). Для curl/API сохранён Basic Auth:
`curl -u admin:bjorn http://[ip]:8000/version`. Подробности — в
[Политике безопасности](SECURITY.md). Сменить пароль можно также через
страницу конфигурации в самом веб-интерфейсе.

##### 3.3: Headless-режим (без e-Paper HAT, v1.4.0)

Чтобы запустить Bjorn **без e-Paper дисплея** (RPi 4, серверы, тестирование),
установите в `shared_config.json`:

```json
"epd_type": "none"
```

EPD-инициализация пропускается, display-поток не стартует, веб-интерфейс
становится основным. Рендер экрана всё равно пишется в `web/screen.png`
(для веб-UI).

##### 3.4: Несколько подсетей (v1.4.0)

По умолчанию сканер сканирует автоматически определённую подсеть. Чтобы
указать свой список, добавьте в `shared_config.json`:

```json
"custom_subnets": ["192.168.1.0/24", "10.0.0.0/24"]
```

Пустой список = авто-детект (поведение по умолчанию).

##### 3.5: Preview-режим / эмулятор экрана (v1.4.0)

Для разработки и тестирования без e-Paper HAT установите `"epd_type":"preview"`.
Загружается mock-драйвер, display-поток запускается полностью и пишет кадры
в `web/screen.png`. Экран виден через вкладку Bjorn в веб-интерфейсе.

#### Шаг 4: Настройка лимитов файловых дескрипторов

Для предотвращения ошибки `OSError: [Errno 24] Too many open files` необходимо увеличить лимиты файловых дескрипторов.

##### 4.1: Изменение лимитов файловых дескрипторов для всех пользователей

Отредактируйте `/etc/security/limits.conf`:

```bash
sudo vi /etc/security/limits.conf
```

Добавьте следующие строки:

```
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
```

##### 4.2: Настройка лимитов Systemd

Отредактируйте `/etc/systemd/system.conf`:

```bash
sudo vi /etc/systemd/system.conf
```

Раскомментируйте и измените:

```
DefaultLimitNOFILE=65535
```

Отредактируйте `/etc/systemd/user.conf`:

```bash
sudo vi /etc/systemd/user.conf
```

Раскомментируйте и измените:

```
DefaultLimitNOFILE=65535
```

##### 4.3: Создание или изменение `/etc/security/limits.d/90-nofile.conf`

```bash
sudo vi /etc/security/limits.d/90-nofile.conf
```

Добавьте:

```
root soft nofile 65535
root hard nofile 65535
```

##### 4.4: Настройка системного лимита файловых дескрипторов

Отредактируйте `/etc/sysctl.conf`:

```bash
sudo vi /etc/sysctl.conf
```

Добавьте:

```
fs.file-max = 2097152
```

Примените изменения:

```bash
sudo sysctl -p
```

#### Шаг 5: Перезагрузка Systemd и применение изменений

Перезагрузите systemd для применения новых лимитов:

```bash
sudo systemctl daemon-reload
```

#### Шаг 6: Изменение файлов конфигурации PAM

PAM (Pluggable Authentication Modules) управляет тем, как лимиты применяются к пользовательским сессиям. Чтобы новые лимиты файловых дескрипторов вступили в силу, обновите следующие файлы конфигурации.

##### Шаг 6.1: Отредактируйте `/etc/pam.d/common-session` и `/etc/pam.d/common-session-noninteractive`

```bash
sudo vi /etc/pam.d/common-session
sudo vi /etc/pam.d/common-session-noninteractive
```

Добавьте эту строку в конец обоих файлов:

```
session required pam_limits.so
```

Это обеспечит применение лимитов из `/etc/security/limits.conf` для всех пользовательских сессий.

#### Шаг 7: Настройка сервисов

##### 7.1: Сервис Bjorn

Создайте файл сервиса:

```bash
sudo vi /etc/systemd/system/bjorn.service
```

Добавьте следующее содержимое:

```ini
[Unit]
Description=Bjorn Service
DefaultDependencies=no
Before=basic.target
After=local-fs.target

[Service]
ExecStartPre=/home/bjorn/Bjorn/kill_port_8000.sh
ExecStart=/usr/bin/python3 /home/bjorn/Bjorn/Bjorn.py
WorkingDirectory=/home/bjorn/Bjorn
StandardOutput=inherit
StandardError=inherit
Restart=always
User=root

# Проверка открытых файлов и перезапуск при достижении лимита (буфер ulimit -n в 1000)
ExecStartPost=/bin/bash -c 'FILE_LIMIT=$(ulimit -n); THRESHOLD=$(( FILE_LIMIT - 1000 )); while :; do TOTAL_OPEN_FILES=$(lsof | wc -l); if [ "$TOTAL_OPEN_FILES" -ge "$THRESHOLD" ]; then echo "File descriptor threshold reached: $TOTAL_OPEN_FILES (threshold: $THRESHOLD). Restarting service."; systemctl restart bjorn.service; exit 0; fi; sleep 10; done &'

[Install]
WantedBy=multi-user.target
```



##### 7.2: Скрипт освобождения порта 8000

Создайте скрипт для освобождения порта 8000:

```bash
vi /home/bjorn/Bjorn/kill_port_8000.sh
```

Добавьте:

```bash
#!/bin/bash
PORT=8000
PIDS=$(lsof -t -i:$PORT)

if [ -n "$PIDS" ]; then
    echo "Killing PIDs using port $PORT: $PIDS"
    kill -9 $PIDS
fi
```

Сделайте скрипт исполняемым:

```bash
chmod +x /home/bjorn/Bjorn/kill_port_8000.sh
```


##### 7.3: Настройка USB Gadget

Измените `/boot/firmware/cmdline.txt`:

```bash
sudo vi /boot/firmware/cmdline.txt
```

Добавьте следующее сразу после `rootwait`:

```
modules-load=dwc2,g_ether
```

Измените `/boot/firmware/config.txt`:

```bash
sudo vi /boot/firmware/config.txt
```

Добавьте в конец файла:

```
dtoverlay=dwc2
```

Создайте скрипт USB gadget:

```bash
sudo vi /usr/local/bin/usb-gadget.sh
```

Добавьте следующее содержимое:

```bash
#!/bin/bash
set -e

modprobe libcomposite
cd /sys/kernel/config/usb_gadget/
mkdir -p g1
cd g1

echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

mkdir -p strings/0x409
echo "fedcba9876543210" > strings/0x409/serialnumber
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "Pi Zero USB" > strings/0x409/product

mkdir -p configs/c.1/strings/0x409
echo "Config 1: ECM network" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

mkdir -p functions/ecm.usb0

# Проверка существующей символической ссылки и удаление при необходимости
if [ -L configs/c.1/ecm.usb0 ]; then
    rm configs/c.1/ecm.usb0
fi
ln -s functions/ecm.usb0 configs/c.1/

# Ожидание освобождения устройства перед перечислением USB-контроллеров
max_retries=10
retry_count=0

while ! ls /sys/class/udc > UDC 2>/dev/null; do
    if [ $retry_count -ge $max_retries ]; then
        echo "Error: Device or resource busy after $max_retries attempts."
        exit 1
    fi
    retry_count=$((retry_count + 1))
    sleep 1
done

# Проверка, настроен ли уже интерфейс usb0
if ! ip addr show usb0 | grep -q "172.20.2.1"; then
    ifconfig usb0 172.20.2.1 netmask 255.255.255.0
else
    echo "Interface usb0 already configured."
fi
```

Сделайте скрипт исполняемым:

```bash
sudo chmod +x /usr/local/bin/usb-gadget.sh
```

Создайте systemd-сервис:

```bash
sudo vi /etc/systemd/system/usb-gadget.service
```

Добавьте:

```ini
[Unit]
Description=USB Gadget Service
After=network.target

[Service]
ExecStartPre=/sbin/modprobe libcomposite
ExecStart=/usr/local/bin/usb-gadget.sh
Type=simple
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Настройте `usb0`:

```bash
sudo vi /etc/network/interfaces
```

Добавьте:

```bash
allow-hotplug usb0
iface usb0 inet static
    address 172.20.2.1
    netmask 255.255.255.0
```

Перезагрузите сервисы:

```bash
sudo systemctl daemon-reload
sudo systemctl enable systemd-networkd
sudo systemctl enable usb-gadget
sudo systemctl start systemd-networkd
sudo systemctl start usb-gadget
```

Для использования в качестве USB gadget необходимо выполнить перезагрузку.
###### Настройка Windows PC

Установите статический IP-адрес на вашем Windows PC:

- **IP-адрес**: `172.20.2.2`
- **Маска подсети**: `255.255.255.0`
- **Шлюз по умолчанию**: `172.20.2.1`
- **DNS-серверы**: `8.8.8.8`, `8.8.4.4`

---

## 📜 Лицензия

2024 infinition, 2026 Chumikov Sec — Bjorn распространяется под лицензией MIT. Подробности см. в файле [LICENSE](LICENSE).
