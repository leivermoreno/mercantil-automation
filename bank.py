import logging
import re


import yaml
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support import expected_conditions
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger("main").getChild(__name__)


class Bank:
    _LOGIN_URL = "https://www30.mercantilbanco.com/melp/login"
    _BASE_URL = "https://www30.mercantilbanco.com/melp/summary"
    _BUTTON_SUBMIT_SELECTOR = (By.CSS_SELECTOR, "#app-container .btn-primary")

    def __init__(self) -> None:
        self._bank_code = None
        self._ci = None
        self._phone = None
        self._amount = None
        self._USERNAME = None
        self._PASSWORD = None
        self._SECURITY_QUESTIONS = None
        self._driver = None
        self._wait = None
        self.balance = None
        self._OVERLAY_VISIBILITY_EC = expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, "app melp-loading .overlay")
        )

        logger.debug("Mercantil object instantiated.")

    def _get_driver_options(self) -> ChromeOptions:
        options = ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_argument("--headless")
        options.add_argument("--disable-dev-shm-usage")

        return options

    def start_session(self) -> None:
        logger.debug("Start session.")
        self._load_login_data()
        chrome_service = ChromeService(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(
            service=chrome_service, options=self._get_driver_options()
        )
        logger.debug("Driver initialized.")
        self._wait = WebDriverWait(self._driver, timeout=30)
        self._login()
        self.balance = self._get_balance()

    def _load_login_data(self) -> None:
        with open("data.yaml", "r", encoding="utf8") as f:
            login_info = yaml.load(f, Loader=yaml.FullLoader)
            self._USERNAME = login_info["username"]
            self._PASSWORD = login_info["password"]
            self._SECURITY_QUESTIONS = login_info["security_questions"]
        logger.debug("Login data loaded.")

    def _login(self) -> None:
        logger.debug("Login process started.")
        self._driver.get(self._LOGIN_URL)
        self._wait.until_not(self._OVERLAY_VISIBILITY_EC)

        username_input = self._driver.find_element(by=By.ID, value="username")
        password_input = self._driver.find_element(by=By.ID, value="password")
        button_submit = self._driver.find_element(*self._BUTTON_SUBMIT_SELECTOR)

        username_input.send_keys(self._USERNAME)
        password_input.send_keys(self._PASSWORD)
        button_submit.click()
        logger.debug("Logged in. Proceeding to input security questions.")

        # input security questions
        self._wait.until_not(self._OVERLAY_VISIBILITY_EC)
        question1 = self._driver.find_element(
            by=By.CSS_SELECTOR, value="#question-1 > label"
        ).text
        question2 = self._driver.find_element(
            by=By.CSS_SELECTOR, value="#question-2 > label"
        ).text
        question_input1 = self._driver.find_element(by=By.ID, value="mat-input-3")
        question_input2 = self._driver.find_element(by=By.ID, value="mat-input-4")
        shared_conn_input = self._driver.find_element(
            by=By.CSS_SELECTOR, value="label[for=shared]"
        )
        button_submit = self._driver.find_element(*self._BUTTON_SUBMIT_SELECTOR)

        question_input1.send_keys(self._SECURITY_QUESTIONS[question1])
        question_input2.send_keys(self._SECURITY_QUESTIONS[question2])
        shared_conn_input.click()
        button_submit.click()
        logger.debug("Security question inputted and submitted.")

    def _get_balance(self) -> None:
        logger.debug("Getting balance.")
        self._wait.until_not(self._OVERLAY_VISIBILITY_EC)

        # checking bc may be triggered after a tpago is done to recalculate the balance
        if not self._driver.current_url == self._BASE_URL:
            self._driver.get(self._BASE_URL)

        balance = self._driver.find_element(
            by=By.CSS_SELECTOR, value=".container-petro-currency"
        ).text
        balance = balance[4:].replace(".", "").replace(",", ".")
        logger.info(f"Balance obtained. Current balance is Bs. {balance}.")
        return float(balance)

    def tpago(self, bank_code: str, ci: str, phone: str, amount: str) -> str:
        logger.debug("Initiating a tpago transaction.")

        arguments = [bank_code, ci, phone, amount]
        self._validate_tpago_data(*arguments)
        result = self._execute_tpago(*arguments)

        # calling to recalculate balance
        self._get_balance()

        logger.info(f"Tpago executed. Result: {result}")
        return result

    def _validate_tpago_data(
        self, bank_code: str, ci: str, phone: str, amount: str
    ) -> None:
        logger.debug("Validating data for tpago.")
        err_msg = []

        is_match = isinstance(bank_code, str) and re.search(
            r"^0105|0102|0104|0108|0114|0115|0128|0134|0137|0138|0145|0151|0156|0157|"
            r"0163|0166|0168|0169|0171|0172|0174|0175|0177|0191$",
            bank_code,
        )
        if not is_match:
            err_msg.append("Invalid bank code.")

        is_match = isinstance(ci, str) and re.search(r"^\d{7,8}$", ci)
        if not is_match:
            err_msg.append("Invalid CI.")

        is_match = isinstance(phone, str) and re.search(
            r"^(0412|04141|0424|0416)\d{7}$", phone
        )
        if not is_match:
            err_msg.append("Invalid phone number.")

        is_match = isinstance(amount, str) and re.search(r"^\d{1,4}(\.\d{2})?$", amount)
        amount_flt = float(amount)
        if not is_match:
            err_msg.append("Invalid amount.")

        enough_balance = self.balance >= amount_flt + amount_flt * 0.003
        if not enough_balance:
            err_msg.append("Balance is not enough.")

        if len(err_msg) > 0:
            raise ValueError("The input data is wrong: %s" % ", ".join(err_msg))

    def _execute_tpago(
        self, bank_code: str, ci: str, phone: str, amount: str
    ) -> int | str:
        logger.debug("Executing tpago transaction.")
        self._driver.get(self._BASE_URL + "tpago")
        self._wait.until_not(self._OVERLAY_VISIBILITY_EC)

        # selecting account
        account_select = self._driver.find_element(by=By.ID, value="mat-select-0")
        account_select.click()
        account_option = self._driver.find_element(by=By.ID, value="mat-option-0")
        account_option.click()
        # selecting phone prefix
        phone_prefix_select = self._driver.find_element(by=By.ID, value="mat-select-2")
        phone_prefix_select.click()
        phone_prefix_options = self._driver.find_elements(
            by=By.CSS_SELECTOR, value="#mat-select-2-panel mat-option"
        )
        phone_prefix_option = None
        for option in phone_prefix_options:
            if option.text == phone[0:4]:
                phone_prefix_option = option
                break
        phone_prefix_option.click()
        # input phone number
        phone_number_input = self._driver.find_element(by=By.ID, value="mat-input-1")
        phone_number_input.send_keys(phone[4:])
        # input ci | assuming the ci is always Venezuelan
        ci_input = self._driver.find_element(by=By.ID, value="mat-input-2")
        ci_input.send_keys(ci)
        # selecting bank code
        bank_select = self._driver.find_element(by=By.ID, value="mat-select-6")
        bank_select.click()
        bank_options = self._driver.find_elements(
            by=By.CSS_SELECTOR, value="#mat-select-6-panel mat-option"
        )
        bank_option = None
        for option in bank_options:
            is_match = re.search(r"%s" % bank_code, option.text)
            if is_match:
                bank_option = option
                break
        bank_option.click()
        # input amount
        amount_input = self._driver.find_element(by=By.ID, value="mat-input-3")
        amount_input.send_keys(amount)
        # input description
        description_input = self._driver.find_element(by=By.ID, value="mat-input-4")
        description_input.send_keys("Pago")
        # submit the form
        button_submit = self._driver.find_element(*self._BUTTON_SUBMIT_SELECTOR)
        button_submit.click()
        logger.debug("Tpago data inputted and submitted.")

        # confirm pago movil
        self._wait.until_not(self._OVERLAY_VISIBILITY_EC)
        button_submit = self._driver.find_element(*self._BUTTON_SUBMIT_SELECTOR)
        button_submit.click()

        # TODO: check if sites is no longer in maintenance and finish this section

        # return result
