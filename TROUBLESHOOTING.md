# 🐛 Известные проблемы и устранение неполадок

<p align="center">
  <img src="https://github.com/user-attachments/assets/c5eb4cc1-0c3d-497d-9422-1614651a84ab" alt="thumbnail_IMG_0546" width="98">
</p>

## 📚 Содержание

- [Известные проблемы при разработке](#-известные-проблемы-при-разработке)
- [Устранение неполадок](#-устранение-неполадок)
- [Лицензия](#-лицензия)

## 🪲 Известные проблемы при разработке

### Проблема длительной работы

- **Проблема**: `OSError: [Errno 24] Too many open files`
- **Статус**: Частично решено настройкой системных лимитов.
- **Обходной путь**: Увеличены лимиты файловых дескрипторов.
- **Мониторинг**: Проверить количество открытых файлов: `lsof -p $(pgrep -f Bjorn.py) | wc -l`
- В данный момент логи периодически показывают эту информацию как (FD : XXX)

## 🛠️ Устранение неполадок

### Проблемы с сервисом

```bash
# Просмотр логов сервиса Bjorn
journalctl -fu bjorn.service

# Проверка статуса сервиса
sudo systemctl status bjorn.service

# Подробные логи в реальном времени
sudo journalctl -u bjorn.service -f

# или

sudo tail -f /home/bjorn/Bjorn/data/logs/*

# Проверка использования порта 8000
sudo lsof -i :8000
```

### Проблемы с дисплеем

```bash
# Проверка SPI-устройств
ls /dev/spi*

# Проверка прав пользователя
sudo usermod -a -G spi,gpio bjorn
```

### Проблемы с сетью

```bash
# Проверка сетевых интерфейсов
ip addr show

# Проверка USB gadget-интерфейса
ip link show usb0
```

### Проблемы с правами

```bash
# Исправление владельца
sudo chown -R bjorn:bjorn /home/bjorn/Bjorn

# Исправление прав доступа
sudo chmod -R 755 /home/bjorn/Bjorn
```

### 🖥️ Если экран не загорается

Если после загрузки RPi экран остаётся чёрным больше минуты — выполните
диагностику в следующем порядке:

**Шаг 1. Проверь журнал сервиса** (самый важный шаг):

```bash
sudo journalctl -u bjorn.service --no-pager | tail -50
```

Что искать:
- `status=203/EXEC` → нет executable bit на `kill_port_8000.sh`.
  Лечится `sudo chmod +x /home/bjorn/Bjorn/kill_port_8000.sh` или
  обновлением до v1.3.2+.
- `ImportError` / `SyntaxError` → проблема в коде. Обновись до последнего
  релиза: `cd /home/bjorn/Bjorn && git fetch --tags && git checkout v1.3.3`.
- Сервис не пишет ничего → падает ДО Python, смотри следующий шаг.

**Шаг 2. Проверь последний Bjorn-лог**:

```bash
sudo tail -5 /home/bjorn/Bjorn/data/logs/Bjorn.py.log
```

Что искать:
- Последняя строка `Starting the web server...` → main thread выходит
  сразу после старта (нет `bjorn_thread.join()` в `__main__`). Лечится
  обновлением до v1.3.3+.
- Файл пустой или циклически переписывается → crash-loop (см. ниже).

**Шаг 3. Проверь права на startup-скрипты**:

```bash
ls -la /home/bjorn/Bjorn/kill_port_8000.sh /home/bjorn/Bjorn/Bjorn.py
# Должно быть -rwxr-xr-x. Если -rw-r--r-- — нет executable bit.
sudo chmod +x /home/bjorn/Bjorn/kill_port_8000.sh /home/bjorn/Bjorn/Bjorn.py
sudo systemctl restart bjorn.service
```

### 🔁 Crash-loop: как распознать

**Признаки**:
- `Bjorn.py.log` пустой, `shared.py.log` содержит многократно
  повторяющийся цикл инициализации (`Loading configuration...` →
  `Initializing EPD display...` → снова `Loading configuration...`)
- В `journalctl` видны частые restart-ы (каждые 5-10 секунд)
- Экран всё время чёрный или мигает

**Частые причины** (в порядке частоты):
1. **Executable bit сброшен** на `kill_port_8000.sh` после `git pull`
   → `status=203/EXEC`. Лечится `chmod +x` или обновлением до v1.3.2+.
2. **Main thread выходит сразу** (daemon threads + нет join)
   → лечится обновлением до v1.3.3+.
3. **SyntaxError / ImportError** в одном из модулей. Смотри полный
   traceback в `journalctl -u bjorn.service`.

### 🔄 После `apt full-upgrade`

На RPi OS Bookworm с firmware 2024+ (особенно на RPi 5 / BCM2712) файл
`/proc/cpuinfo` **больше не содержит** строку "Raspberry". Старые версии
Bjorn (до v1.3.1) падали на определении платы:

```
ERROR - Error initializing EPD display: Cannot find sysfs_software_spi.so
```

**Проверка, что проблема именно в этом**:
```bash
cat /etc/rpi-issue    # должен показать "Raspberry Pi reference ..."
grep Raspberry /proc/cpuinfo    # на RPi 5 с новой firmware - пусто
```

**Fix**: обновиться до v1.3.1+, где добавлен multi-source platform
detection (`/proc/cpuinfo` + `/etc/rpi-issue` + `/proc/device-tree/model`).

---

## 📜 Лицензия

2024 infinition, 2026 Chumikov Sec — Bjorn распространяется под лицензией MIT. Подробности см. в файле [LICENSE](LICENSE).
