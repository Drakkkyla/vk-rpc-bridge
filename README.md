# VK Discord RPC Bridge 🎵🚀

Программа для отображения текущего трека из VK Music в статусе Discord с настраиваемым Rich Presence. Современный интерфейс с анимациями, автоматическим обновлением и поддержкой темной темы.

![image](https://github.com/user-attachments/assets/c1efcdcd-7118-4059-b1e8-0023157e18ff)

Основные возможности ✨ 

- Автоматический Rich Presence 
  Показывает текущий трек, исполнителя и прогресс воспроизведения в реальном времени
- Системный трей 📳  
  Сворачивание в трей с уведомлениями о смене треков
- Авто-переподключение 🔌  
  Самостоятельно восстанавливает связь с Discord при разрыве
- Кастомизация статуса 🎨  
  Настраиваемые форматы отображения (поддержка темной/светлой тем)
- Веб-сервер 🌐  
  Встроенная поддержка интеграции через localhost:8112
- Логирование 📝  
  Подсвеченные логи с фильтрацией по уровням важности

Технологии 🛠️

- Python 3.8+
- PyQt5 (GUI)
- Discord RPC API
- Socket.IO (веб-сервер)
- Plyer (уведомления)
- Асинхронная обработка событий

 Установка и запуск 🚀

1. Клонируйте репозиторий:
```bash
git clone https://github.com/ваш-логин/vk-discord-rpc.git 
cd vk-discord-rpc

```

2. Установите расширение:
```bash
Установка Tampermonkey: https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo
После этого, установите расширение: // ==UserScript==
// @name         Vk Music RPC hook
// @namespace    http://tampermonkey.net/
// @version      2.0.0
// @description  This extension is a hook for the vk-discord-rpc project on github
// @author       TofaDev, Suburbanno
// @updateURL    https://raw.githubusercontent.com/Suburbanno/vk-music-rpc/main/vk-extension.js
// @downloadURL  https://raw.githubusercontent.com/Suburbanno/vk-music-rpc/main/vk-extension.js
// @match        *://vk.com/*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=vk.com
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @require      https://cdn.socket.io/4.0.0/socket.io.min.js
// ==/UserScript==

const getCurrentPlayingMusic = () => {
  var wrap = document.querySelector(".top_audio_player_title_wrap");
  var textMusicDiv = wrap.querySelector("div");

  return textMusicDiv.textContent;
};

const musicIsPlaying = (musicPlayer) => {
  return musicPlayer.classList.contains("top_audio_player_playing");
};

let serverUrl = GM_getValue("serverUrl", "ws://localhost:8112");

GM_registerMenuCommand("Set the websocket server address", () => {
  let url = prompt(
    "Enter the address for the websocket server in the format: ws://host:port",
    serverUrl
  );
  if (url) {
    serverUrl = url;
    GM_setValue("serverUrl", url);
  }
});

(function () {
  "use strict";

  const musicPlayer = document.getElementById("top_audio_player");

  if (!musicPlayer) return;

  const socket = io.connect(serverUrl);

  socket.on("connect", () => {
    console.log("connected to vk-discord-rpc server");

    let lastSong = null;
    let isSongPaused = false;

    setInterval(() => {
      if (!musicIsPlaying(musicPlayer)) {
        if (!isSongPaused) {
          socket.emit("song_paused", "song is paused");
          isSongPaused = true;
        }
        lastSong = null;
        return;
      }

      isSongPaused = false;

      let currentSong = getCurrentPlayingMusic();

      if (lastSong === currentSong) return;

      lastSong = currentSong;

      let splittedSong = currentSong.split("—");

      socket.emit("song_changed", {
        artist: splittedSong[0],
        songName: splittedSong[1],
        source: "VK",
      });
    }, 500);
  });
})();

```

- Включите отображение прослушиваний в настройках VK

- Убедитесь что Discord запущен


 Использование 🎮
- Запустите сервер через кнопку "Запустить сервер"
- Авторизуйтесь в VK через браузер
- Наслаждайтесь автоматическим обновлением статуса



Сделано с ❤️ by Drakkk & cassius
