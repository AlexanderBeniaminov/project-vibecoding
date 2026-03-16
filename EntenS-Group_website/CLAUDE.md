# CLAUDE.md — EntenS Group Landing Page

> Этот файл читается автоматически. Полная документация → `project.md`. ТЗ → `brief.md`.

---

## ФАЙЛОВАЯ СТРУКТУРА

```
EntenS-Group_website/
├── index.html          ← ЕДИНСТВЕННЫЙ рабочий файл сайта
├── CLAUDE.md           ← этот файл (читается автоматически)
├── project.md          ← структурированная документация проекта
├── brief.md            ← полное ТЗ от клиента
├── research.md         ← исследование конкурентов и рынка
└── DESIGN_TRENDS_2025.md ← дизайн-тренды 2025–2026
```

Весь сайт — **один файл `index.html`**: HTML + `<style>` + `<script>` внутри. Не создавать отдельные CSS/JS файлы без явной просьбы.

---

## ПРАВИЛА РАБОТЫ С КОДОМ

1. **Перед любым изменением** — прочитать нужный блок `index.html`, не редактировать вслепую
2. **Стек: Vanilla HTML/CSS/JS** — никаких React, Vue, Svelte
3. **GSAP CDN** уже подключён (или должен быть): GSAP 3 + ScrollTrigger + SplitText + Lenis
4. **Один файл** — всё в `index.html`. Исключение: медиафайлы (фото, видео)
5. **Mobile-first** — верстать от 375px, расширять вверх

---

## ДИЗАЙН-СИСТЕМА (быстрый доступ)

```css
/* Фоны секций */
#hero, #contact, footer → bg: #212121 (тёмный)
#about, #why, #cases    → bg: #FFFFFF (белый)
#portfolio, #for-investors, #team, #geography → bg: #F5F9F5 (светлый)
#numbers, #for-owners   → bg: #FFFFFF

/* Главные цвета */
--green-primary: #4CAF50;  /* кнопки, иконки, активные элементы */
--green-deep:    #2E7D32;  /* hover */
--green-lime:    #8BC34A;  /* теги, бейджи */
--text-primary:  #212121;
--border:        rgba(46, 125, 50, 0.15);

/* Шрифты */
Заголовки → Cormorant Garamond (Google Fonts, кириллица)
Всё остальное → Inter (Google Fonts, кириллица)
```

---

## СТРУКТУРА СЕКЦИЙ (якоря)

```
header (sticky)
#hero          → dark, орбы, H1 split-анимация, trust bar
#numbers       → white, count-up метрики
#about         → white, текст 60% + фото 40%
#portfolio     → light, 5 карточек (горизонтальный scroll на desktop / swipe на mobile)
#for-owners    → white, форматы сделки (покупка / аренда с выкупом), 3-шаговый процесс
#for-investors → light, 3 формата участия (проекты / соинвест / партнёрство)
#why           → white, bento grid 6 тайлов
#cases         → white, кейсы До→Что→Результат
#team          → light, 3–4 карточки с фото
#geography     → white, SVG-карта России
#contact       → dark, форма 4 поля + контакты
footer         → dark
```

---

## КНОПКИ

```css
/* Primary — основное действие */
background: #4CAF50; color: #fff;
hover: background: #2E7D32; transform: translateY(-2px);

/* Ghost на светлом фоне */
background: transparent; color: #4CAF50; border: 2px solid #4CAF50;
hover: background: #4CAF50; color: #fff;

/* Ghost на тёмном фоне */
background: transparent; color: #fff; border: 1px solid rgba(255,255,255,0.5);
hover: background: #fff; color: #212121;

/* Общее */
border-radius: 8px; padding: 14px 28px;
font-family: Inter; font-weight: 600; font-size: 15px;
transition: all 0.25s ease;
```

---

## АНИМАЦИИ — ЧТО РЕАЛИЗОВАНО / ЧТО НАДО

### Must Have (если не реализовано — добавить)
- Hero H1: GSAP SplitText, по словам, stagger 80ms, translateY(30px→0) + opacity(0→1)
- Trust bar числа: count-up от 0 при scroll-into-view (easeOut)
- Секции: IntersectionObserver → fade-in + translateY(20px→0)
- Портфель карточки: 3D tilt при mousemove
- Ambient orbs: CSS keyframes float, 25s и 35s цикл
- Sticky header: backdrop-filter blur(20px) + тень после скролла
- Portfolio desktop: GSAP ScrollTrigger горизонтальный scroll
- **Всегда:** `@media (prefers-reduced-motion: reduce)` отключает все анимации

### Should Have
- Magnetic CTA кнопки (60px radius)
- Custom cursor (28px → 80px "VIEW" на карточках портфеля, только `@media (hover: hover)`)
- Floating Telegram-кнопка: появляется через 3 сек или после 50% скролла

---

## ФОРМА (#contact)

4 поля: Имя · Телефон/email · Кто вы (dropdown) · О ситуации (textarea, необязательно)
+ чекбокс 152-ФЗ + кнопка полной ширины
После submit → success-сообщение **без перезагрузки** (скрыть форму, показать сообщение)
Валидация: HTML5 + кастомные сообщения зелёного цвета
Отправка: `fetch` → Telegram Bot API (или заглушка если токена нет)

---

## МОБИЛЬНАЯ ВЕРСИЯ

```
< 480px:   1 колонка, hero H1 36px, portfolio → swipe carousel (Embla/Splide)
480–768px: 2 колонки карточек
768–1024px: tablet, 2–3 колонки
> 1024px:  desktop, горизонтальный scroll портфеля
```

- Touch targets: минимум 44x44px
- inputs: `font-size: 16px` (без zoom на iOS)
- Горизонтальный overflow → запрещён
- Бургер-меню на мобильном, CTA-кнопка в header остаётся видимой

---

## КОНТЕНТ-ПЛЕЙСХОЛДЕРЫ (не трогать без данных от клиента)

Эти данные **не придуманы** — ждём от клиента:
- Конкретные цифры в trust bar (годы, объекты, гости/год, города)
- Фото объектов и команды
- Телефон, email, Telegram username
- Юридические реквизиты (ОГРН, ИНН)
- Кейсы с реальными результатами

Пока — использовать `[X]`, `[Название объекта]`, `[Город]` и т.д. — чтобы было очевидно, что нужно заменить.

---

## ЗАПРЕЩЕНО

- Autoplay видео со звуком
- Pop-up в первые 30 сек
- > 5 пунктов в основной навигации
- > 4 полей в форме
- "Команда профессионалов", "индивидуальный подход" — без конкретики
- Stock-фото
- Единственный канал связи (только форма)
- Горизонтальный overflow на мобильном

---

## БЫСТРЫЕ ОТВЕТЫ НА ЧАСТЫЕ ВОПРОСЫ

**Q: Какой фреймворк?**
A: Никакого. Vanilla HTML/CSS/JS.

**Q: Сколько файлов?**
A: Один — `index.html`. Всё внутри.

**Q: Куда отправляется форма?**
A: Telegram Bot API через fetch. Токен бота — предоставит клиент.

**Q: Какая библиотека для карусели на мобильном?**
A: Embla Carousel или Splide (CDN). Предпочесть Splide — легче.

**Q: Нужен ли билд/сборщик?**
A: Нет. Файл открывается напрямую в браузере.
