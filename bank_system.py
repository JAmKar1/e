import sqlite3
import hashlib
import getpass
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import sys
import time


class DatabaseManager:
    def __init__(self, db_name='bank.db'):
        self.db_name = db_name
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    date_of_birth TEXT NOT NULL,
                    street TEXT NOT NULL,
                    city TEXT NOT NULL,
                    zip_code TEXT NOT NULL,
                    country TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    email TEXT NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            ''')

            # Таблица счетов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    account_number TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    account_type TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    balance REAL DEFAULT 0,
                    overdraft_limit REAL DEFAULT 0,
                    created_date TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Таблица транзакций
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_number TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (account_number) REFERENCES accounts(account_number)
                )
            ''')

            conn.commit()
            print(f"✅ База данных инициализирована: {self.db_name}")

    def execute_query(self, query, params=(), fetchone=False, fetchall=False):
        """Выполнение SQL запроса"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetchone:
                return cursor.fetchone()
            elif fetchall:
                return cursor.fetchall()
            else:
                conn.commit()
                return cursor.lastrowid

    def fetch_all_dict(self, query, params=()):
        """Получение всех записей в виде словарей"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


class UserService:
    def __init__(self):
        self.db = DatabaseManager()

    def hash_password(self, password):
        """Хеширование пароля"""
        return hashlib.sha256(password.encode()).hexdigest()

    def register_user(self, user_data):
        """Регистрация нового пользователя"""
        try:
            # Проверка уникальности имени пользователя
            check_query = "SELECT id FROM users WHERE username = ?"
            existing = self.db.execute_query(check_query, (user_data['username'],), fetchone=True)

            if existing:
                return False, "Имя пользователя уже занято"

            # Хеширование пароля
            password_hash = self.hash_password(user_data['password'])

            # Вставка пользователя
            query = '''
                INSERT INTO users (
                    first_name, last_name, date_of_birth,
                    street, city, zip_code, country,
                    phone_number, email, username, password_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''

            params = (
                user_data['first_name'], user_data['last_name'], user_data['date_of_birth'],
                user_data['street'], user_data['city'], user_data['zip_code'], user_data['country'],
                user_data['phone_number'], user_data['email'], user_data['username'], password_hash
            )

            user_id = self.db.execute_query(query, params)
            return True, f"Пользователь успешно зарегистрирован! ID: {user_id}"

        except sqlite3.Error as e:
            return False, f"Ошибка базы данных: {e}"

    def authenticate(self, username, password):
        """Аутентификация пользователя"""
        query = '''
            SELECT id, first_name, last_name, username, password_hash
            FROM users WHERE username = ?
        '''

        result = self.db.execute_query(query, (username,), fetchone=True)

        if not result:
            return None

        user_id, first_name, last_name, username_db, password_hash = result

        if self.hash_password(password) == password_hash:
            return {
                'id': user_id,
                'first_name': first_name,
                'last_name': last_name,
                'username': username_db
            }

        return None

    def get_user_info(self, user_id):
        """Получение информации о пользователе"""
        query = "SELECT * FROM users WHERE id = ?"
        result = self.db.fetch_all_dict(query, (user_id,))
        return result[0] if result else None


class BankService:
    def __init__(self):
        self.db = DatabaseManager()

    def generate_account_number(self):
        """Генерация номера счета"""
        import random
        return f"40817810{random.randint(10000000, 99999999)}"

    def create_account(self, user_id, account_type, currency, overdraft_limit=0):
        """Создание нового счета"""
        try:
            account_number = self.generate_account_number()
            created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            query = '''
                INSERT INTO accounts (
                    account_number, user_id, account_type,
                    currency, balance, overdraft_limit, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            '''

            params = (
                account_number, user_id, account_type,
                currency, 0, overdraft_limit, created_date
            )

            self.db.execute_query(query, params)
            return True, f"Счет успешно создан! Номер: {account_number}"

        except sqlite3.Error as e:
            return False, f"Ошибка при создании счета: {e}"

    def get_accounts(self, user_id):
        """Получение всех счетов пользователя"""
        query = '''
            SELECT account_number, account_type, currency, 
                   balance, overdraft_limit, created_date
            FROM accounts WHERE user_id = ?
        '''
        return self.db.fetch_all_dict(query, (user_id,))

    def get_account(self, account_number):
        """Получение информации о счете"""
        query = "SELECT * FROM accounts WHERE account_number = ?"
        result = self.db.fetch_all_dict(query, (account_number,))
        return result[0] if result else None

    def deposit(self, account_number, amount, description=""):
        """Пополнение счета"""
        if amount <= 0:
            return False, "Сумма должна быть положительной"

        try:
            # Начало транзакции
            account = self.get_account(account_number)
            if not account:
                return False, "Счет не найден"

            # Обновление баланса
            update_query = '''
                UPDATE accounts 
                SET balance = balance + ? 
                WHERE account_number = ?
            '''
            self.db.execute_query(update_query, (amount, account_number))

            # Запись транзакции
            trans_query = '''
                INSERT INTO transactions 
                (account_number, transaction_type, amount, description, timestamp)
                VALUES (?, 'DEPOSIT', ?, ?, ?)
            '''
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_query(trans_query,
                                  (account_number, amount, description, timestamp))

            return True, f"Счет пополнен на {amount} {account['currency']}"

        except sqlite3.Error as e:
            return False, f"Ошибка при пополнении: {e}"

    def withdraw(self, account_number, amount, description=""):
        """Снятие денег со счета"""
        if amount <= 0:
            return False, "Сумма должна быть положительной"

        try:
            account = self.get_account(account_number)
            if not account:
                return False, "Счет не найден"

            available = account['balance'] + account['overdraft_limit']

            if amount > available:
                return False, f"Недостаточно средств. Доступно: {available} {account['currency']}"

            # Обновление баланса
            update_query = '''
                UPDATE accounts 
                SET balance = balance - ? 
                WHERE account_number = ?
            '''
            self.db.execute_query(update_query, (amount, account_number))

            # Запись транзакции
            trans_query = '''
                INSERT INTO transactions 
                (account_number, transaction_type, amount, description, timestamp)
                VALUES (?, 'WITHDRAWAL', ?, ?, ?)
            '''
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_query(trans_query,
                                  (account_number, amount, description, timestamp))

            return True, f"Со счета снято {amount} {account['currency']}"

        except sqlite3.Error as e:
            return False, f"Ошибка при снятии: {e}"

    def transfer(self, from_account, to_account, amount, description=""):
        """Перевод между счетами"""
        if amount <= 0:
            return False, "Сумма должна быть положительной"

        try:
            # Проверка существования счетов
            from_acc = self.get_account(from_account)
            to_acc = self.get_account(to_account)

            if not from_acc:
                return False, f"Счет отправителя {from_account} не найден"
            if not to_acc:
                return False, f"Счет получателя {to_account} не найден"

            # Проверка валюты
            if from_acc['currency'] != to_acc['currency']:
                return False, "Нельзя переводить между счетами с разной валютой"

            # Проверка доступных средств
            available = from_acc['balance'] + from_acc['overdraft_limit']
            if amount > available:
                return False, f"Недостаточно средств на счете отправителя. Доступно: {available}"

            # Снятие с первого счета
            success, message = self.withdraw(from_account, amount,
                                             f"Перевод на счет {to_account}. {description}")
            if not success:
                return False, message

            # Зачисление на второй счет
            success, message = self.deposit(to_account, amount,
                                            f"Перевод со счета {from_account}. {description}")
            if not success:
                # Откат если не удалось зачислить
                self.deposit(from_account, amount, "Откат перевода")
                return False, "Ошибка при переводе: не удалось зачислить средства"

            return True, f"Перевод {amount} {from_acc['currency']} выполнен успешно"

        except sqlite3.Error as e:
            return False, f"Ошибка при переводе: {e}"

    def get_transactions(self, account_number, limit=10):
        """Получение истории транзакций"""
        query = '''
            SELECT transaction_type, amount, description, timestamp
            FROM transactions 
            WHERE account_number = ?
            ORDER BY timestamp DESC
            LIMIT ?
        '''
        return self.db.fetch_all_dict(query, (account_number, limit))

    def get_account_owner(self, account_number):
        """Получение владельца счета"""
        query = '''
            SELECT u.first_name, u.last_name, u.username
            FROM accounts a
            JOIN users u ON a.user_id = u.id
            WHERE a.account_number = ?
        '''
        result = self.db.execute_query(query, (account_number,), fetchone=True)
        return result if result else None


class BankSystemCLI:
    def __init__(self):
        self.user_service = UserService()
        self.bank_service = BankService()
        self.current_user = None

    def clear_screen(self):
        """Очистка экрана"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_header(self, title):
        """Вывод заголовка"""
        print("\n" + "=" * 60)
        print(f" {title}".center(60))
        print("=" * 60)

    def print_menu(self, options):
        """Вывод меню"""
        print("\n" + "-" * 40)
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
        print("-" * 40)

    def get_input(self, prompt, password=False):
        """Получение ввода - ПРОСТАЯ ВЕРСИЯ"""
        if password:
            # Для пароля просто показываем приглашение
            print(prompt, end="")
            return input()
        else:
            return input(prompt).strip()

    def wait_for_enter(self):
        """Ожидание нажатия Enter"""
        input("\nНажмите Enter для продолжения...")

    def show_message(self, message, is_success=True):
        """Показать сообщение"""
        symbol = "✅" if is_success else "❌"
        print(f"\n{symbol} {message}")
        self.wait_for_enter()

    def register_user(self):
        """Регистрация нового пользователя"""
        self.clear_screen()
        self.print_header("РЕГИСТРАЦИЯ НОВОГО ПОЛЬЗОВАТЕЛЯ")

        print("\nЗаполните данные для регистрации:")

        user_data = {}
        user_data['first_name'] = self.get_input("Имя: ")
        user_data['last_name'] = self.get_input("Фамилия: ")
        user_data['date_of_birth'] = self.get_input("Дата рождения (дд.мм.гггг): ")
        user_data['street'] = self.get_input("Улица: ")
        user_data['city'] = self.get_input("Город: ")
        user_data['zip_code'] = self.get_input("Почтовый индекс: ")
        user_data['country'] = self.get_input("Страна: ")
        user_data['phone_number'] = self.get_input("Телефон: ")
        user_data['email'] = self.get_input("Email: ")
        user_data['username'] = self.get_input("Логин: ")
        user_data['password'] = self.get_input("Пароль: ", password=True)

        # Подтверждение пароля
        confirm_password = self.get_input("Подтвердите пароль: ", password=True)

        if user_data['password'] != confirm_password:
            self.show_message("Пароли не совпадают!", False)
            return

        # Регистрация пользователя
        success, message = self.user_service.register_user(user_data)
        self.show_message(message, success)

    def login(self):
        """Вход в систему - ПРОСТАЯ ВЕРСИЯ БЕЗ GETPASS"""
        self.clear_screen()
        self.print_header("ВХОД В СИСТЕМУ")

        print("\n" + "=" * 40)
        print("ТЕСТОВЫЕ ДАННЫЕ (если создавали):")
        print("=" * 40)
        print("1. Логин: ivanov")
        print("   Пароль: password123")
        print("\n2. Логин: petrova")
        print("   Пароль: qwerty456")
        print("=" * 40)

        print("\n" + "➡" * 20)
        print("ШАГ 1: ВВЕДИТЕ ЛОГИН")
        username = input("Логин: ").strip()
        print(f"✓ Принято: '{username}'")

        print("\n" + "➡" * 20)
        print("ШАГ 2: ВВЕДИТЕ ПАРОЛЬ")
        password = input("Пароль: ").strip()  # Просто input, пароль будет виден
        print(f"✓ Пароль получен (длина: {len(password)} символов)")

        print("\n" + "➡" * 20)
        print("ШАГ 3: ПРОВЕРКА ДАННЫХ...")
        time.sleep(1)  # Небольшая пауза для эффекта

        user = self.user_service.authenticate(username, password)

        if user:
            self.current_user = user
            print("\n" + "✅" * 25)
            print("✅ ВХОД ВЫПОЛНЕН УСПЕШНО!")
            print("✅" * 25)
            print(f"\nДобро пожаловать, {user['first_name']} {user['last_name']}!")
            print(f"Ваш логин: {user['username']}")
            print(f"ID пользователя: {user['id']}")

            print("\n" + "⏳" * 20)
            print("Переход в главное меню через 3 секунды...")
            for i in range(3, 0, -1):
                print(f"Осталось: {i} секунд", end="\r")
                time.sleep(1)
            print(" " * 30)  # Очистка строки

            return True
        else:
            print("\n" + "❌" * 25)
            print("❌ ОШИБКА ВХОДА!")
            print("❌" * 25)
            print("\nВозможные причины:")
            print("1. Неправильный логин или пароль")
            print("2. Пользователь не существует")
            print("3. База данных пуста")
            print("\nПопробуйте:")
            print("- Проверить раскладку клавиатуры")
            print("- Создать тестовые данные (пункт 3 в главном меню)")
            print("- Зарегистрировать нового пользователя")

            self.wait_for_enter()
            return False

    def logout(self):
        """Выход из системы"""
        self.current_user = None
        print("\n✅ Вы успешно вышли из системы!")
        self.wait_for_enter()

    def show_accounts(self):
        """Показать счета пользователя"""
        self.clear_screen()
        self.print_header("МОИ СЧЕТА")

        accounts = self.bank_service.get_accounts(self.current_user['id'])

        if not accounts:
            print("\nУ вас нет открытых счетов.")
            print("Создайте новый счет в меню.")
        else:
            print(f"\nНайдено счетов: {len(accounts)}")
            print("\n" + "-" * 80)
            print(f"{'Номер счета':<20} {'Тип':<12} {'Валюта':<8} {'Баланс':<12} {'Лимит':<10} {'Дата создания':<15}")
            print("-" * 80)

            for acc in accounts:
                print(f"{acc['account_number']:<20} "
                      f"{acc['account_type']:<12} "
                      f"{acc['currency']:<8} "
                      f"{acc['balance']:<12.2f} "
                      f"{acc['overdraft_limit']:<10.2f} "
                      f"{acc['created_date'][:10]:<15}")

        self.wait_for_enter()

    def create_account(self):
        """Создание нового счета"""
        self.clear_screen()
        self.print_header("СОЗДАНИЕ НОВОГО СЧЕТА")

        print("\nВыберите тип счета:")
        print("1. Расчетный счет (Checking)")
        print("2. Сберегательный счет (Savings)")
        print("3. Депозитный счет (Deposit)")

        choice = self.get_input("\nВаш выбор (1-3): ")

        account_types = {
            '1': 'Checking',
            '2': 'Savings',
            '3': 'Deposit'
        }

        if choice not in account_types:
            print("\n❌ Неверный выбор!")
            self.wait_for_enter()
            return

        print("\nВыберите валюту:")
        print("1. RUB (Рубли)")
        print("2. USD (Доллары)")
        print("3. EUR (Евро)")

        currency_choice = self.get_input("\nВаш выбор (1-3): ")

        currencies = {
            '1': 'RUB',
            '2': 'USD',
            '3': 'EUR'
        }

        if currency_choice not in currencies:
            print("\n❌ Неверный выбор!")
            self.wait_for_enter()
            return

        # Запрос лимита овердрафта (только для расчетного счета)
        overdraft_limit = 0
        if choice == '1':
            overdraft_input = self.get_input("Лимит овердрафта (по умолчанию 0): ")
            try:
                overdraft_limit = float(overdraft_input) if overdraft_input else 0
            except ValueError:
                print("\n❌ Неверный формат суммы!")
                self.wait_for_enter()
                return

        # Создание счета
        success, message = self.bank_service.create_account(
            self.current_user['id'],
            account_types[choice],
            currencies[currency_choice],
            overdraft_limit
        )

        print(f"\n{'✅' if success else '❌'} {message}")
        self.wait_for_enter()

    def deposit_money(self):
        """Пополнение счета"""
        self.clear_screen()
        self.print_header("ПОПОЛНЕНИЕ СЧЕТА")

        accounts = self.bank_service.get_accounts(self.current_user['id'])

        if not accounts:
            print("\nУ вас нет открытых счетов.")
            self.wait_for_enter()
            return

        print("\nВаши счета:")
        for i, acc in enumerate(accounts, 1):
            print(f"{i}. {acc['account_number']} ({acc['currency']}) - Баланс: {acc['balance']:.2f}")

        try:
            choice = int(self.get_input("\nВыберите счет для пополнения: ")) - 1
            if choice < 0 or choice >= len(accounts):
                raise ValueError
        except ValueError:
            print("\n❌ Неверный выбор!")
            self.wait_for_enter()
            return

        account = accounts[choice]

        amount_input = self.get_input(f"\nСумма пополнения ({account['currency']}): ")
        try:
            amount = float(amount_input)
            if amount <= 0:
                raise ValueError
        except ValueError:
            print("\n❌ Неверная сумма!")
            self.wait_for_enter()
            return

        description = self.get_input("Описание операции (необязательно): ")

        success, message = self.bank_service.deposit(
            account['account_number'],
            amount,
            description
        )

        print(f"\n{'✅' if success else '❌'} {message}")
        self.wait_for_enter()

    def withdraw_money(self):
        """Снятие денег со счета"""
        self.clear_screen()
        self.print_header("СНЯТИЕ ДЕНЕГ СО СЧЕТА")

        accounts = self.bank_service.get_accounts(self.current_user['id'])

        if not accounts:
            print("\nУ вас нет открытых счетов.")
            self.wait_for_enter()
            return

        print("\nВаши счета:")
        for i, acc in enumerate(accounts, 1):
            available = acc['balance'] + acc['overdraft_limit']
            print(f"{i}. {acc['account_number']} ({acc['currency']}) - "
                  f"Доступно: {available:.2f}")

        try:
            choice = int(self.get_input("\nВыберите счет для снятия: ")) - 1
            if choice < 0 or choice >= len(accounts):
                raise ValueError
        except ValueError:
            print("\n❌ Неверный выбор!")
            self.wait_for_enter()
            return

        account = accounts[choice]
        available = account['balance'] + account['overdraft_limit']

        amount_input = self.get_input(f"\nСумма снятия ({account['currency']}, доступно: {available:.2f}): ")
        try:
            amount = float(amount_input)
            if amount <= 0:
                raise ValueError
        except ValueError:
            print("\n❌ Неверная сумма!")
            self.wait_for_enter()
            return

        description = self.get_input("Описание операции (необязательно): ")

        success, message = self.bank_service.withdraw(
            account['account_number'],
            amount,
            description
        )

        print(f"\n{'✅' if success else '❌'} {message}")
        self.wait_for_enter()

    def transfer_money(self):
        """Перевод денег между счетами"""
        self.clear_screen()
        self.print_header("ПЕРЕВОД ДЕНЕГ")

        # Получаем счета пользователя
        accounts = self.bank_service.get_accounts(self.current_user['id'])

        if not accounts:
            print("\nУ вас нет открытых счетов.")
            self.wait_for_enter()
            return

        print("\nВаши счета:")
        for i, acc in enumerate(accounts, 1):
            available = acc['balance'] + acc['overdraft_limit']
            print(f"{i}. {acc['account_number']} ({acc['currency']}) - "
                  f"Доступно: {available:.2f}")

        try:
            from_choice = int(self.get_input("\nВыберите счет отправителя: ")) - 1
            if from_choice < 0 or from_choice >= len(accounts):
                raise ValueError
        except ValueError:
            print("\n❌ Неверный выбор счета!")
            self.wait_for_enter()
            return

        from_account = accounts[from_choice]

        # Ввод счета получателя
        to_account_number = self.get_input("\nНомер счета получателя: ").strip()

        # Проверка существования счета получателя
        to_account = self.bank_service.get_account(to_account_number)
        if not to_account:
            print(f"\n❌ Счет {to_account_number} не найден!")
            self.wait_for_enter()
            return

        # Получение информации о владельце счета
        owner_info = self.bank_service.get_account_owner(to_account_number)
        if owner_info:
            print(f"\nПолучатель: {owner_info[0]} {owner_info[1]} (@{owner_info[2]})")

        # Ввод суммы
        amount_input = self.get_input(f"\nСумма перевода ({from_account['currency']}): ")
        try:
            amount = float(amount_input)
            if amount <= 0:
                raise ValueError
        except ValueError:
            print("\n❌ Неверная сумма!")
            self.wait_for_enter()
            return

        description = self.get_input("Описание перевода (необязательно): ")

        # Подтверждение
        print(f"\nПодтвердите перевод:")
        print(f"От: {from_account['account_number']}")
        print(f"Кому: {to_account_number}")
        print(f"Сумма: {amount} {from_account['currency']}")

        confirm = self.get_input("\nВы уверены? (да/нет): ").lower()

        if confirm not in ['да', 'yes', 'y', 'д']:
            print("\n❌ Перевод отменен!")
            self.wait_for_enter()
            return

        success, message = self.bank_service.transfer(
            from_account['account_number'],
            to_account_number,
            amount,
            description
        )

        print(f"\n{'✅' if success else '❌'} {message}")
        self.wait_for_enter()

    def show_transactions(self):
        """Показать историю транзакций"""
        self.clear_screen()
        self.print_header("ИСТОРИЯ ОПЕРАЦИЙ")

        accounts = self.bank_service.get_accounts(self.current_user['id'])

        if not accounts:
            print("\nУ вас нет открытых счетов.")
            self.wait_for_enter()
            return

        print("\nВаши счета:")
        for i, acc in enumerate(accounts, 1):
            print(f"{i}. {acc['account_number']} ({acc['currency']})")

        try:
            choice = int(self.get_input("\nВыберите счет для просмотра истории: ")) - 1
            if choice < 0 or choice >= len(accounts):
                raise ValueError
        except ValueError:
            print("\n❌ Неверный выбор!")
            self.wait_for_enter()
            return

        account = accounts[choice]
        transactions = self.bank_service.get_transactions(account['account_number'], 20)

        if not transactions:
            print(f"\nПо счету {account['account_number']} нет операций.")
        else:
            print(f"\nПоследние операции по счету {account['account_number']}:")
            print("\n" + "-" * 80)
            print(f"{'Дата':<20} {'Тип':<12} {'Сумма':<12} {'Описание':<30}")
            print("-" * 80)

            for trans in transactions:
                amount_str = f"{trans['amount']:+.2f}" if trans[
                                                              'transaction_type'] != 'TRANSFER' else f"{trans['amount']:.2f}"
                print(f"{trans['timestamp']:<20} "
                      f"{trans['transaction_type']:<12} "
                      f"{amount_str:<12} "
                      f"{trans['description'][:30]:<30}")

        self.wait_for_enter()

    def show_user_info(self):
        """Показать информацию о пользователе"""
        self.clear_screen()
        self.print_header("МОЙ ПРОФИЛЬ")

        user_info = self.user_service.get_user_info(self.current_user['id'])

        if user_info:
            print(f"\nЛичная информация:")
            print(f"  Имя: {user_info['first_name']} {user_info['last_name']}")
            print(f"  Дата рождения: {user_info['date_of_birth']}")
            print(f"  Логин: {user_info['username']}")
            print(f"  Email: {user_info['email']}")
            print(f"  Телефон: {user_info['phone_number']}")

            print(f"\nАдрес:")
            print(f"  Улица: {user_info['street']}")
            print(f"  Город: {user_info['city']}")
            print(f"  Индекс: {user_info['zip_code']}")
            print(f"  Страна: {user_info['country']}")
        else:
            print("\n❌ Не удалось загрузить информацию о пользователе.")

        self.wait_for_enter()

    def create_sample_data(self):
        """Создание тестовых данных"""
        self.clear_screen()
        self.print_header("СОЗДАНИЕ ТЕСТОВЫХ ДАННЫХ")

        print("\nСоздание тестовых пользователей...")

        # Первый тестовый пользователь
        user1_data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'date_of_birth': '15.05.1990',
            'street': 'ул. Ленина, д. 10',
            'city': 'Москва',
            'zip_code': '101000',
            'country': 'Россия',
            'phone_number': '+79161234567',
            'email': 'ivanov@example.com',
            'username': 'ivanov',
            'password': 'password123'
        }

        success1, message1 = self.user_service.register_user(user1_data)
        print(f"{'✅' if success1 else '❌'} {message1}")

        # Второй тестовый пользователь
        user2_data = {
            'first_name': 'Мария',
            'last_name': 'Петрова',
            'date_of_birth': '22.08.1985',
            'street': 'пр. Мира, д. 25',
            'city': 'Санкт-Петербург',
            'zip_code': '190000',
            'country': 'Россия',
            'phone_number': '+78129876543',
            'email': 'petrova@example.com',
            'username': 'petrova',
            'password': 'qwerty456'
        }

        success2, message2 = self.user_service.register_user(user2_data)
        print(f"{'✅' if success2 else '❌'} {message2}")

        print("\nСоздание тестовых счетов...")

        # Аутентификация первого пользователя для создания счетов
        user1 = self.user_service.authenticate('ivanov', 'password123')
        if user1:
            # Создание счета для Иванова
            self.bank_service.create_account(user1['id'], 'Checking', 'RUB', 5000)
            self.bank_service.deposit('40817810123456789', 10000, 'Начальный взнос')
            print("✅ Создан счет для Иванова: 40817810123456789")

        # Аутентификация второго пользователя
        user2 = self.user_service.authenticate('petrova', 'qwerty456')
        if user2:
            # Создание счета для Петровой
            self.bank_service.create_account(user2['id'], 'Savings', 'RUB')
            self.bank_service.deposit('40817810987654321', 5000, 'Начальный взнос')
            print("✅ Создан счет для Петровой: 40817810987654321")

        print("\n✅ Тестовые данные созданы!")
        print("\nТестовые пользователи:")
        print("1. Логин: ivanov, Пароль: password123")
        print("2. Логин: petrova, Пароль: qwerty456")

        self.wait_for_enter()

    def main_menu(self):
        """Главное меню (неавторизованный пользователь)"""
        while True:
            self.clear_screen()
            self.print_header("БАНКОВСКАЯ СИСТЕМА")

            # Показываем текущего пользователя если есть
            if self.current_user:
                print(f"\n⚠️ ВНИМАНИЕ: Вы уже вошли как {self.current_user['username']}")
                print("Если хотите выйти - выберите пункт 'Выйти' в меню пользователя")
                print("-" * 40)

            options = [
                "Вход в систему",
                "Регистрация",
                "Создать тестовые данные",
                "Выход"
            ]

            self.print_menu(options)

            choice = self.get_input("Выберите действие (1-4): ")
            print(f"\nВы выбрали: {choice}")

            if choice == '1':
                print("Запускаю процедуру входа...")
                if self.login():
                    print(f"\n✓ Успешный вход! Запускаю меню пользователя...")
                    self.user_menu()
                else:
                    print(f"\n✗ Вход не удался, возвращаюсь в главное меню...")
            elif choice == '2':
                self.register_user()
            elif choice == '3':
                self.create_sample_data()
            elif choice == '4':
                print("\n✅ До свидания!")
                sys.exit(0)
            else:
                print("\n❌ Неверный выбор!")
                self.wait_for_enter()

    def user_menu(self):
        """Меню авторизованного пользователя - С ПРОВЕРКОЙ"""
        if not self.current_user:
            print("\n❌ ОШИБКА: current_user не установлен!")
            print("Возвращаюсь в главное меню...")
            self.wait_for_enter()
            return

        print(f"\n✓ DEBUG: В user_menu(), пользователь: {self.current_user['username']}")

        while self.current_user:
            self.clear_screen()
            welcome_msg = f"Добро пожаловать, {self.current_user['first_name']} {self.current_user['last_name']}!"
            self.print_header(welcome_msg)

            print(f"\nИнформация о сессии:")
            print(f"ID: {self.current_user['id']}")
            print(f"Логин: {self.current_user['username']}")
            print("-" * 40)

            options = [
                "Мои счета",
                "Создать новый счет",
                "Пополнить счет",
                "Снять деньги",
                "Перевод денег",
                "История операций",
                "Мой профиль",
                "Выйти из системы"
            ]

            self.print_menu(options)

            choice = self.get_input("Выберите действие (1-8): ")
            print(f"Выбрано: {choice}")

            if choice == '1':
                self.show_accounts()
            elif choice == '2':
                self.create_account()
            elif choice == '3':
                self.deposit_money()
            elif choice == '4':
                self.withdraw_money()
            elif choice == '5':
                self.transfer_money()
            elif choice == '6':
                self.show_transactions()
            elif choice == '7':
                self.show_user_info()
            elif choice == '8':
                print(f"\nЗавершаю сессию пользователя {self.current_user['username']}...")
                self.logout()
                break
            else:
                print("\n❌ Неверный выбор!")
                self.wait_for_enter()


    def run(self):
        """Запуск системы"""
        self.main_menu()


def show_welcome():
    """Показать приветственное сообщение"""
    print("\n" + "=" * 60)
    print("""
     ____             _    _                   
    |  _ \           | |  (_)                  
    | |_) | __ _  ___| | ___ _ __   __ _       
    |  _ < / _` |/ __| |/ / | '_ \ / _` |      
    | |_) | (_| | (__|   <| | | | | (_| |      
    |____/ \__,_|\___|_|\_\_|_| |_|\__, |      
                                    __/ |      
                                   |___/       
    """)
    print("=" * 60)
    print("БАНКОВСКАЯ СИСТЕМА - ТЕРМИНАЛЬНАЯ ВЕРСИЯ".center(60))
    print("=" * 60)

    print("\n⚡ Система запускается...")
    time.sleep(1)


if __name__ == "__main__":
    show_welcome()

    # Запуск системы
    try:
        system = BankSystemCLI()
        system.run()
    except KeyboardInterrupt:
        print("\n\n👋 Программа завершена пользователем")
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {e}")
        print("Попробуйте удалить файл bank.db и запустить заново")
        input("Нажмите Enter для выхода...")