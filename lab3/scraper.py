import pandas as pd
from playwright.sync_api import sync_playwright, Response, Route, TimeoutError

# Адреса сторінки пошуку курсів на Coursera
start_url = "https://www.coursera.org/search?query=python"

# Назва CSV-файлу, у який будуть збережені результати
target_csv = "courses_list.csv"

# Список для збереження зібраних курсів
collected_items = []

# Множина для зберігання ID курсів, щоб уникнути повторів
seen_ids = set()


# Крок 3. Оптимізація ресурсів та блокування непотрібних файлів
def route_filter(route: Route):
    # Типи ресурсів, які не потрібні для збору інформації
    blocked_types = ["image", "media", "font"]

    # Якщо запит стосується зображень, медіа або шрифтів — блокуємо його
    if route.request.resource_type in blocked_types:
        route.abort()
    else:
        # Усі інші запити дозволяємо
        route.continue_()


# Крок 4. Перетворення тривалості курсу
def format_duration(value):
    # Якщо тривалість відсутня, повертаємо відповідний текст
    if not value:
        return "Не вказано"

    # Словник для перетворення кодів тривалості на зрозумілі назви
    durations = {
        "LESS_THAN_TWO_HOURS": "Менше 2 годин",
        "ONE_TO_FOUR_WEEKS": "1–4 тижні",
        "ONE_TO_THREE_MONTHS": "1–3 місяці",
        "THREE_TO_SIX_MONTHS": "3–6 місяців",
        "SIX_TO_TWELVE_MONTHS": "6–12 місяців",
        "ONE_TO_THREE_YEARS": "1–3 роки"
    }

    # Повертаємо переклад тривалості або початкове значення,
    # якщо його немає у словнику
    return durations.get(value, value)


# Крок 5. Отримання інформації про курси з JSON
def extract_courses(data):

    # Якщо отримані дані є списком, перебираємо кожен його елемент
    if isinstance(data, list):
        for element in data:
            extract_courses(element)

    # Якщо дані є словником, перевіряємо його вміст
    elif isinstance(data, dict):

        # Перевіряємо, чи є поточний об'єкт інформацією про курс
        if data.get("__typename") == "Search_ProductHit":

            # Отримуємо унікальний ідентифікатор курсу
            course_id = data.get("id")

            # Перевіряємо, чи є ID і чи не був курс зібраний раніше
            if course_id and course_id not in seen_ids:
                seen_ids.add(course_id)

                # Отримуємо назву курсу
                name = data.get("translatedName") or data.get("name")

                # Отримуємо організації-партнери курсу
                partners = data.get("partners") or []
                author = ", ".join(partners) if partners else "Не вказано"

                # Отримуємо тривалість курсу
                duration = (
                    data.get("productDuration")
                    or data.get("duration")
                )

                # Отримуємо середній рейтинг та кількість оцінок
                rating = data.get("avgProductRating")
                ratings_count = data.get("numProductRatings")

                # Формуємо інформацію про рейтинг
                if rating is not None and ratings_count is not None:
                    rating_info = f"{rating:.2f} ({ratings_count} оцінок)"
                elif rating is not None:
                    rating_info = round(rating, 2)
                elif ratings_count is not None:
                    rating_info = f"{ratings_count} оцінок"
                else:
                    rating_info = "Не вказано"

                # Додаємо отриману інформацію до загального списку
                collected_items.append({
                    "id": course_id,
                    "Назва курсу": name,
                    "Інструктор/Автор": author,
                    "Тривалість": format_duration(duration),
                    "Кількість слухачів/Рейтинг": rating_info
                })

        # Перевіряємо всі вкладені елементи словника
        # Це дозволяє знаходити курси на різних рівнях JSON
        for value in data.values():
            if isinstance(value, (dict, list)):
                extract_courses(value)


# Крок 6. Перехоплення мережевих відповідей
def handle_network_response(response: Response):

    # Перевіряємо, чи є запит потрібним і чи успішно його виконано
    if "graphql-gateway" in response.url and response.status == 200:

        # Отримуємо тип вмісту відповіді сервера
        content_type = response.headers.get("content-type", "")

        # Перевіряємо, чи відповідь містить JSON
        if "application/json" in content_type:
            try:
                # Перетворюємо відповідь сервера на Python-об'єкт
                payload = response.json()

                # Запам'ятовуємо кількість курсів до обробки відповіді
                before = len(collected_items)

                # Передаємо JSON для пошуку та збору курсів
                extract_courses(payload)

                # Обчислюємо кількість нових курсів
                new_count = len(collected_items) - before

                # Виводимо повідомлення, якщо знайдено нові курси
                if new_count > 0:
                    print(f"[+] Перехоплено нових курсів: {new_count}")

            except Exception as err:
                # Виводимо повідомлення у разі помилки обробки JSON
                print(f"[-] Помилка обробки JSON: {err}")


# Крок 7. Запуск браузера та відкриття сторінки
with sync_playwright() as p:

    # Запускаємо браузер Chromium
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )

    # Створюємо контекст браузера із заданим розміром вікна
    context = browser.new_context(
        viewport={"width": 1440, "height": 900}
    )

    # Створюємо нову сторінку
    page = context.new_page()

    # Встановлюємо фільтр для блокування непотрібних ресурсів
    page.route("**/*", route_filter)

    # Підключаємо обробник, який відстежує мережеві відповіді
    page.on("response", handle_network_response)

    print(f"[*] Відкриваємо каталог: {start_url}")

    try:
        # Відкриваємо сторінку та очікуємо завантаження основного HTML
        page.goto(
            start_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

    except TimeoutError:
        # Обробляємо ситуацію, якщо сторінка не відкрилася вчасно
        print("[-] Таймаут під час відкриття сторінки")
        browser.close()
        raise SystemExit(1)

    # Очікуємо завантаження перших результатів пошуку
    page.wait_for_timeout(4000)

    # Крок 8. Прокручування сторінки для завантаження додаткових курсів
    print("[*] Поступовий скрол сторінки...")

    # Виконуємо чотири прокручування сторінки вниз
    for i in range(4):
        page.evaluate("window.scrollBy(0, 1000)")
        page.wait_for_timeout(1500)
        print(f"[*] Скролінг {i + 1}/4")

    # Повертаємо сторінку на початок
    page.evaluate("window.scrollTo(0, 0)")

    # Очікуємо завершення останніх мережевих відповідей
    page.wait_for_timeout(1000)


# Крок 9. Очищення та збереження результатів у CSV
if collected_items:

    # Створюємо таблицю з отриманого списку курсів
    df = pd.DataFrame(collected_items)

    # Видаляємо записи, у яких відсутня назва курсу
    df = df.dropna(subset=["Назва курсу"])

    # Видаляємо повтори за ідентифікатором курсу
    df = df.drop_duplicates(subset=["id"])

    # Залишаємо лише потрібні для звіту стовпці
    df = df[
        [
            "Назва курсу",
            "Інструктор/Автор",
            "Тривалість",
            "Кількість слухачів/Рейтинг"
        ]
    ]

    # Зберігаємо таблицю у CSV-файл
    df.to_csv(
        target_csv,
        index=False,
        encoding="utf-8-sig",
        sep=";"
    )

    # Виводимо підсумкову інформацію про виконання програми
    print("\n================================")
    print(f"[✓] Зібрано курсів: {len(df)}")
    print(f"[✓] Файл збережено: {target_csv}")
    print("================================")

else:
    # Повідомляємо, якщо курси не вдалося знайти
    print("[-] Курси не знайдено. Перевірте мережеві запити.")
