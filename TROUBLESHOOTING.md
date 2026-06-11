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

---

## 📜 Лицензия

2024 infinition, 2026 Chumikov — Bjorn распространяется под лицензией MIT. Подробности см. в файле [LICENSE](LICENSE).
