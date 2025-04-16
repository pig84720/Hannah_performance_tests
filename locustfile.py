from locust import HttpUser, task, between, SequentialTaskSet
import random
import json

def load_config():
    config_path = "configs/environment.json"
    try:
        with open(config_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Configuration file not found: {config_path}")
        exit(1)

class ShoppingFlow(SequentialTaskSet):
    connection_timeout = 5  # 連線超時設定為 5 秒
    network_timeout = 15    # 讀取超時設定為 10 秒

    def on_start(self):
        """
        用戶啟動時進行註冊與登入操作，並初始化必要的數據
        """
        # 隨機生成帳號與密碼
        self.account = f"test_user_{random.randint(1, 100000)}"
        self.password = "test_password"

        # 註冊用戶
        register_payload = {
            "account": self.account,
            "password": self.password,
            "name": "Test User",
            "addr": "Test Address",
            "area_id": 1,
            "birthday": "2000-01-01",
            "cel": "0912345678",
            "city_id": 1,
            "email": f"{self.account}@example.com",
            "tel": "0123456789"
        }
        response = self.client.post(
            "/member/sign_up",
            json=register_payload,
            name="User Sign Up",
            timeout=(self.connection_timeout, self.network_timeout)
        )
        
        # 登入並獲取 JWT Token
        login_payload = {"account": self.account, "password": self.password}
        login_response = self.client.post(
            "/member/sign_in",
            json=login_payload,
            name="User Sign In",
            timeout=(self.connection_timeout, self.network_timeout)
        )
        if login_response.status_code == 200:
            self.token = login_response.json().get("data", {}).get("access_token", "")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.stop()  # 登入失敗，停止該虛擬用戶

        # 初始化商品列表和訂單ID
        self.product_ids = []
        self.order_id = None

    @task(2)
    def browse_products(self):
        """
        瀏覽商品列表，並提取商品ID
        """
        response = self.client.get(
            "/product/get_product_list",
            headers=self.headers,
            name="Browse Product List",
            timeout=(self.connection_timeout, self.network_timeout)
        )
        if response.status_code == 200:
            product_list = response.json().get("data", [])
            if product_list:
                self.product_ids = [product["product_id"] for product in product_list]  # 提取商品ID
        else:
            print("Failed to fetch product list")

    @task(2)
    def view_product_details(self):
        """
        隨機查看商品詳情
        """
        if self.product_ids:
            product_id = random.choice(self.product_ids)
            self.client.get(
                f"/product/get_product_info/{product_id}",
                headers=self.headers,
                name="View Product Details",
                timeout=(self.connection_timeout, self.network_timeout)
            )

    @task(2)
    def add_to_cart(self):
        """
        隨機將商品加入購物車
        """
        if self.product_ids:
            product_id = random.choice(self.product_ids)
            payload = {"account": self.account, "product_id": product_id, "quantity": 1}
            self.client.post(
                "/cart/add",
                json=payload,
                headers=self.headers,
                name="Add to Cart",
                timeout=(self.connection_timeout, self.network_timeout)
            )

    @task(1)
    def checkout(self):
        """
        建立訂單並獲取訂單ID，處理商品數量不足的情況
        """
        # 檢查購物車是否有商品
        cart_response = self.client.get(
            f"/cart/get_list?account={self.account}",
            headers=self.headers,
            name="Get Cart Details",
            timeout=(self.connection_timeout, self.network_timeout)
        )
        if cart_response.status_code == 200:
            cart_data = cart_response.json().get("data", [])
            if not cart_data:
                print("Cart is empty. Skipping checkout.")
                # 補充購物車流程
                self.add_to_cart()
                return
        else:
            print("Failed to fetch cart details. Skipping checkout.")
            return

        # 建立訂單
        create_order_response = self.client.post(
            f"/order/create_order/{self.account}",
            headers=self.headers,
            name="Create Order",
            timeout=(self.connection_timeout, self.network_timeout)
        )
        if create_order_response.status_code == 200:
            self.order_id = create_order_response.json().get("data", {}).get("order_id", "")
            print(f"Order created successfully with ID: {self.order_id}")
        elif create_order_response.status_code == 400:
            print("Failed to create order: Insufficient stock.")
        else:
            print(f"Unexpected error during order creation: {create_order_response.status_code}")

        # 查看訂單詳情
        if self.order_id:
            self.client.get(
                f"/order/order_detail/{self.order_id}",
                headers=self.headers,
                name="View Order Details",
                timeout=(self.connection_timeout, self.network_timeout)
            )

    @task(1)
    def clear_cart(self):
        """
        清空購物車
        """
        self.client.delete(
            f"/cart/clear?account={self.account}",
            headers=self.headers,
            name="Clear Cart",
            timeout=(self.connection_timeout, self.network_timeout)
        )


class ShoppingUser(HttpUser):
    # 從單一配置檔案中讀取 base_url
    config = load_config()
    host = config["base_url"]  # 設定 base URL
    tasks = [ShoppingFlow]
    wait_time = between(1, 3)