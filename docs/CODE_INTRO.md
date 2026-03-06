# 项目代码介绍（顺带学 Python）

面向：想看懂这个交易机器人怎么跑、同时当 Python 入门材料的人。按「从入口到依赖」的顺序讲，并标出常见的 Python 用法。

---

## 如果你会 Java / Kotlin / TypeScript：先看这句对照

| Python | Java | Kotlin | TypeScript |
|--------|------|--------|------------|
| `def f(x: int) -> str:` | `String f(int x)` | `fun f(x: Int): String` | `function f(x: number): string` |
| `x: str`、`-> dict` | 类型写在前面 | 同左 | 同左 |
| `None` | `null` | `null` | `null` |
| `if not x:` | `if (!x)` | `if (!x)` | `if (!x)` |
| `dict` | `Map` / `HashMap` | `Map` / `mutableMapOf` | `Record<string, T>` / `object` |
| `data.get("key")` | `data.get("key")` | `data["key"]` | `data["key"]` / `data?.key` |
| `[]` 空列表 | `new ArrayList<>()` | `emptyList()` | `[]` |
| `{}` 空字典 | `new HashMap<>()` | `emptyMap()` | `{}` |
| `self.xxx` | `this.xxx` | 省略写 `xxx` | `this.xxx` |
| `class A(B):` | `class A extends B` | `class A : B()` | `class A extends B` |
| `@dataclass` | 手写 getter/setter 或 Lombok `@Data` | `data class` | `interface` + 对象字面量 |
| `Enum` | `enum class` | `enum class` | `enum` / 字面量联合类型 |
| `ABC` + `@abstractmethod` | `abstract class` + `abstract method` | `abstract class` | `abstract class` |
| 没有 `;`，缩进即块 | `{}` 表示块 | 同 Java | 同左 |
| `True` / `False` | `true` / `false` | 同左 | `true` / `false` |
| `"a" in data` | `data.containsKey("a")` | `data.containsKey("a")` | `"a" in data` |
| `isinstance(x, dict)` | `x instanceof Map` | `x is Map` | `typeof x === "object"` 等 |

**入口**：就像 Java 的 `main(String[] args)`，这里是 `main()`，参数用 `argparse` 从命令行读（类似 `process.argv` 的解析库）。**跑一次** = 调一次 `main()`；`--interval 60` 就是每 60 秒再调一次 `main()`。

**程序流程一句话**：读 `.monitor_ref.json`（参考价、持仓成本）→ 向 OKX 取当前价 → 策略 `recommend(price)` 得到买/卖/观望 → 若是买/卖且 `--execute`，先做三秒价格确认、滑点检查，卖出再检查利润 > 0.3% → 调 `broker.submit_order` 下单 → 成交后把最新参考价、持仓成本写回 `.monitor_ref.json`。下面正文里的「Python 小知识」可以对照上表看。

---

## 一、项目长什么样（目录）

```
stock_trading_bot/
├── run_okx_live.py      # 你要跑的入口：OKX 涨卖跌买
├── run_binance_live.py  # 币安版，逻辑类似
├── run_backtest.py      # 股票回测入口
├── .env                 # API 密钥（不提交）
├── .monitor_ref.json    # 参考价、持仓成本、持仓量（运行后生成）
└── src/
    ├── strategy/        # 策略：只算「买/卖/观望」，不下单
    │   ├── base.py      # 信号类型、策略基类
    │   └── threshold.py # 涨跌比例策略 SimpleThresholdStrategy
    ├── execution/       # 执行：把「买/卖」变成真实订单
    │   ├── broker_base.py   # 抽象基类
    │   ├── broker_okx.py    # OKX 实现（用 ccxt）
    │   └── order.py         # 订单、状态、买卖方向
    └── risk/            # 风控（回测/股票用得多，OKX 脚本里用得少）
        └── risk_manager.py  # 账户、持仓数据结构
```

**Python 小知识**：`src/` 是一个**包**（package），里面有 `__init__.py`，所以可以写 `from src.strategy import SimpleThresholdStrategy`。

---

## 二、入口脚本在干什么：`run_okx_live.py`

整体流程可以看成：**读配置 → 取价格 → 问策略 → 风控检查 → 下单 → 写状态**。

### 1. 最前面：环境与路径

```python
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
```

- **`Path(__file__).resolve().parent`**：当前脚本所在目录的绝对路径。这样无论从哪执行 `python run_okx_live.py`，都能找到项目根目录。
- **`sys.path.insert(0, ...)`**：把项目根放进模块搜索路径，后面才能 `from src.strategy import ...`。

接着用 `dotenv` 从 `.env` 读 `OKX_API_KEY` 等（若存在）。

**Python 小知识**：`__file__` 是当前 .py 文件的路径；`Path` 是标准库，用来统一处理路径，比手写 `os.path` 更清晰。

---

### 2. 常量和状态文件

```python
MIN_PROFIT_RATIO = 0.003
PRICE_SAMPLES = 3
MONITOR_REF_FILE = Path(__file__).resolve().parent / ".monitor_ref.json"
```

- 用**全大写**表示「常量」，是习惯写法。
- **`Path / ".monitor_ref.json"`**：路径拼接，等价于 `os.path.join(..., ".monitor_ref.json")`。

---

### 3. 读状态：`load_state(symbol)`

```python
def load_state(symbol: str) -> dict:
    if not MONITOR_REF_FILE.exists():
        return {}
    try:
        data = json.loads(MONITOR_REF_FILE.read_text(encoding="utf-8"))
        raw = data.get(symbol)
        if isinstance(raw, dict):
            return raw
        if raw is not None and isinstance(raw, (int, float)):
            return {"reference_price": float(raw)}
        return {}
    except Exception as e:
        _log(f"读取 .monitor_ref.json 失败: {e}")
        return {}
```

- **`symbol: str` / `-> dict`**：类型注解（type hint），方便读代码和 IDE 提示，不写也不会报错。
- **`MONITOR_REF_FILE.read_text(encoding="utf-8")`**：Path 对象的方法，读整个文件为字符串。
- **`json.loads(...)`**：把 JSON 字符串转成 Python 的 dict/list。
- **`data.get(symbol)`**：字典取键，没有则返回 `None`，不会像 `data[symbol]` 那样抛 KeyError。
- **`isinstance(raw, dict)`**：判断类型，避免 `.monitor_ref.json` 里旧格式是数字时当 dict 用导致报错。

**Python 小知识**：用 `get` + `isinstance` 做兼容，是处理「可能脏的数据」的常见写法。

---

### 4. 写状态：`save_state(...)`

```python
def save_state(symbol: str, reference_price: float = None, avg_cost: float = None, position_qty: float = None) -> None:
    data = json.loads(MONITOR_REF_FILE.read_text(...)) if MONITOR_REF_FILE.exists() else {}
    if symbol not in data or not isinstance(data[symbol], dict):
        data[symbol] = {}
    if reference_price is not None:
        data[symbol]["reference_price"] = reference_price
    # ... 同理 avg_cost, position_qty
    MONITOR_REF_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

- **`= None`**：默认参数，调用时可以不传。
- **`json.dumps(..., indent=2)`**：把 dict 转成带缩进的 JSON 字符串，方便人读。
- **`ensure_ascii=False`**：中文等字符不转成 `\uXXXX`，直接保留。

---

### 5. 命令行参数：`argparse`

```python
def main():
    parser = argparse.ArgumentParser(description="OKX：涨卖跌买...")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对")
    parser.add_argument("--ratio", type=float, default=0.5, help="触发比例%%")
    parser.add_argument("--execute", action="store_true", help="是否真实下单")
    parser.add_argument("--interval", type=float, default=0, help="轮询间隔秒")
    args = parser.parse_args()
```

- **`action="store_true"`**：出现 `--execute` 就是 `True`，不出现就是 `False`。
- **`type=float`**：自动把命令行字符串转成浮点数。
- 使用方式：`python run_okx_live.py --symbol BTC/USDT --execute --interval 60`。

**Python 小知识**：`argparse` 是标准库，写小工具时非常常用。

---

### 6. 策略只负责「建议」：`SimpleThresholdStrategy`

```python
from src.strategy import SimpleThresholdStrategy
from src.strategy.base import SignalDirection

state = load_state(args.symbol)
ref_price = state.get("reference_price")
strategy = SimpleThresholdStrategy(ratio_pct=args.ratio, reference_price=ref_price)

text, direction, new_ref = strategy.recommend(price)
# direction 可能是 SignalDirection.LONG（买）、SignalDirection.FLAT（卖）、或 None（观望）
```

- **策略不碰交易所**：只根据「当前价 + 参考价 + 比例」算出一个方向（买/卖/观望）和一句文案。
- **`recommend(price)`** 返回三个东西：`(文案, 方向或 None, 新参考价)`，用元组解包接收。

策略实现见下一节。

---

### 7. 执行层：OKX 下单

```python
from src.execution import OKXBroker
from src.execution.order import OrderSide, OrderState

broker = OKXBroker(api_key=..., api_secret=..., passphrase=..., demo=args.demo)
account = broker.get_account()   # 拿账户权益、现金、持仓
order = broker.submit_order(args.symbol, OrderSide.BUY, qty, price=None, reason=text)
if order.state == OrderState.FILLED:
    # 成交了，更新 avg_cost、position_qty、reference_price，并 save_state
```

- **`price=None`**：表示市价单。
- **`OrderState.FILLED`**：枚举，表示订单已完全成交。用枚举比手写字符串 `"filled"` 更不容易拼错。

**Python 小知识**：`Enum` 把一组固定取值命名，代码里用 `OrderState.FILLED` 比用字符串清晰。

---

### 8. 轮询：递归调用自己

```python
if args.interval > 0:
    _log(f"{args.interval} 秒后再次检查...")
    time.sleep(args.interval)
    return main()
return 0
```

- **`time.sleep(秒数)`**：当前线程暂停，不占 CPU。
- **`return main()`**：递归再跑一遍 main，实现「每隔 N 秒检查一次」。等价于 `while True: ...; time.sleep(interval)`，这里用递归写法。

---

## 三、策略层：`src/strategy/threshold.py`

策略的职责：**给定当前价和参考价，按比例判断买/卖/观望**。

```python
class SimpleThresholdStrategy(StrategyBase):
    def __init__(self, ratio_pct: float = 1.0, reference_price: Optional[float] = None):
        self.ratio_pct = ratio_pct
        self.ratio = ratio_pct / 100.0   # 1.0 -> 0.01
        self.reference_price = reference_price

    def recommend(self, current_price: float) -> tuple[str, Optional[SignalDirection], float]:
        ref = self.reference_price
        if ref is None or ref <= 0:
            self.reference_price = current_price
            return ("暂无参考价，已记录当前价为参考", None, current_price)
        if current_price >= ref * (1 + self.ratio):
            self.reference_price = current_price
            return ("涨了 ≥...，建议卖出", SignalDirection.FLAT, current_price)
        if current_price <= ref * (1 - self.ratio):
            self.reference_price = current_price
            return ("跌了 ≥...，建议买入", SignalDirection.LONG, current_price)
        return ("涨跌未达比例，观望", None, ref)
```

- **`StrategyBase`**：在 `base.py` 里用 `ABC`（抽象基类）定义，要求子类实现 `next()` 等；`recommend()` 是为「单次价格、无 K 线」的监控场景加的接口。
- **`SignalDirection`**：枚举，`LONG`=买，`FLAT`=卖/平仓。
- **`Optional[SignalDirection]`**：类型提示，表示「要么是 SignalDirection，要么是 None」。

**Python 小知识**：`class 子类(父类):` 是继承；`self.xxx` 是实例属性；`Optional[X]` 等价于 `Union[X, None]`。

---

## 四、执行层：`src/execution/`

### 1. 订单与枚举：`order.py`

```python
from enum import Enum
from dataclasses import dataclass

class OrderState(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    # ...

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    state: OrderState = OrderState.PENDING
    filled_quantity: float = 0.0
    filled_avg_price: float = 0.0
    # ...
```

- **`(str, Enum)`**：枚举值同时是字符串，方便和交易所 API 的 `"buy"` / `"filled"` 对齐。
- **`@dataclass`**：自动生成 `__init__`、`__repr__`，少写样板代码，用来放「一堆字段」的数据很合适。

**Python 小知识**：`dataclass` 和 `Enum` 是写「数据结构」和「状态/方向」的常用工具。

---

### 2. 券商抽象：`broker_base.py`

```python
from abc import ABC, abstractmethod

class BrokerBase(ABC):
    @abstractmethod
    def submit_order(self, symbol: str, side: OrderSide, quantity: float, ...) -> Order:
        pass

    @abstractmethod
    def get_account(self) -> AccountState:
        pass
```

- **`ABC`**：抽象基类，不能直接实例化，只能被继承。
- **`@abstractmethod`**：子类必须实现这些方法，否则会报错。这样「回测」用模拟 Broker、「实盘」用 OKXBroker，接口统一。

**Python 小知识**：用抽象基类定义「契约」，多种实现（OKX、币安、模拟）都遵守同一套接口。

---

### 3. OKX 实现：`broker_okx.py`

- 用 **ccxt** 库连 OKX：`ccxt.okx({"apiKey": ..., "secret": ..., "password": passphrase})`。
- **`_get_exchange()`**：懒加载，第一次要下单或查账户时才建连接。
- **`submit_order`**：调 `ex.create_order(symbol, type="market", side="buy", amount=qty)`，然后把返回结果转成我们自己的 `Order` 对象（含 `state`、`filled_quantity`、`filled_avg_price`）。

---

## 五、风控数据结构：`src/risk/risk_manager.py`

OKX 脚本里主要用到的是「账户/持仓」的**数据形状**，而不是完整风控逻辑：

```python
@dataclass
class PositionState:
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float

@dataclass
class AccountState:
    cash: float
    positions: Dict[str, PositionState]   # symbol -> 持仓
    equity: float
```

- **`broker.get_account()`** 返回的就是 `AccountState`，所以脚本里会写 `account.positions.get(args.symbol)`、`account.cash`、`account.equity`。

**Python 小知识**：`Dict[str, PositionState]` 表示「键是 str，值是 PositionState 的字典」，类型提示让代码意图更清楚。

---

## 六、数据流小结（配合学 Python）

1. **入口**：`run_okx_live.py` 的 `main()`，用 `argparse` 解析 `--symbol`、`--execute`、`--interval` 等。
2. **状态**：从 `.monitor_ref.json` 用 `load_state(symbol)` 读参考价、持仓成本、持仓量；成交后用 `save_state(...)` 写回，用到 `Path`、`json`、`dict.get`、`isinstance`。
3. **价格**：通过 `OKXBroker` 拿当前价（或 fallback 到 yfinance），带重试。
4. **策略**：`SimpleThresholdStrategy.recommend(price)` 返回 (文案, 方向, 新参考价)，用到类、枚举、条件判断。
5. **风控**：三秒取样、标准差判插针、买一卖一滑点、卖出前利润率 > 0.3%，都在 `run_okx_live.py` 里用函数封装。
6. **下单**：`broker.submit_order(..., OrderSide.BUY/SELL, qty)`，根据 `Order.state` 是否 `FILLED` 更新状态并 `save_state`。
7. **轮询**：`interval > 0` 时 `time.sleep(interval)` 后 `return main()`。

把「读配置 → 取价 → 策略 → 检查 → 下单 → 写状态」这条线走一遍，再对照上面几处 Python 用法，就能既理解机器人逻辑，又顺带练到：**Path、json、argparse、类型注解、dict、枚举、dataclass、抽象类、异常与重试**。若你想深入某一块（例如只看策略或只看执行），可以指定文件名或模块名，我可以按文件逐段讲。
