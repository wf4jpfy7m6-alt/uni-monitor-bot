"""
aerodrome_monitor.py
Мониторинг застейканной позиции Aerodrome (Base) WETH/USDC в Gauge.
Запуск: python aerodrome_monitor.py
"""

import math
from web3 import Web3

# ── Конфигурация ──────────────────────────────────────────────────────────────

RPC_URL = "https://mainnet.base.org"          # публичный RPC Base
WALLET  = Web3.to_checksum_address("0x1074520dd10d6bad7d760f1762c435f658a8f21a")

# NPM Aerodrome SlipStream
NPM_ADDRESS = Web3.to_checksum_address("0x827922686190790b37229fd06084350E74485b72")

# Пул WETH/USDC CL100
POOL_ADDRESS = Web3.to_checksum_address("0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59")

# Официальный Gauge CL100-WETH/USDC на Base (Aerodrome Finance)
# Источник: basescan.org — "Aerodrome Finance: CL100-WETH/USDC Pool Gauge"
# Если позиция не найдена — скрипт проверит резервный адрес
GAUGE_CANDIDATES = [
    Web3.to_checksum_address("0x1E012d2A200B9c7e0DDc968Eba14e2E7C332A04A"),  # ✅ из NFT transfers (BaseScan)
    Web3.to_checksum_address("0xF33a96b5932D9E9B9A0eDA447AbD8C9d48d2e0c8"),  # резервный
]

# Токены
WETH_ADDRESS = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")
USDC_ADDRESS = Web3.to_checksum_address("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")
AERO_ADDRESS = Web3.to_checksum_address("0x940181a94A35A4569E4529A3CDfB74e38FD98631")

# ── ABI (минимальные) ─────────────────────────────────────────────────────────

GAUGE_ABI = [
    # stakedValues(address owner) → uint256[]
    {
        "inputs": [{"internalType": "address", "name": "depositor", "type": "address"}],
        "name": "stakedValues",
        "outputs": [{"internalType": "uint256[]", "name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    # earned(address token, uint256 tokenId) → uint256
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
        ],
        "name": "earned",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

NPM_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"internalType": "uint96",  "name": "nonce",             "type": "uint96"},
            {"internalType": "address", "name": "operator",          "type": "address"},
            {"internalType": "address", "name": "token0",            "type": "address"},
            {"internalType": "address", "name": "token1",            "type": "address"},
            {"internalType": "int24",   "name": "tickSpacing",       "type": "int24"},
            {"internalType": "int24",   "name": "tickLower",         "type": "int24"},
            {"internalType": "int24",   "name": "tickUpper",         "type": "int24"},
            {"internalType": "uint128", "name": "liquidity",         "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0",       "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1",       "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96",   "type": "uint160"},
            {"internalType": "int24",   "name": "tick",            "type": "int24"},
            {"internalType": "uint16",  "name": "observationIndex","type": "uint16"},
            {"internalType": "uint16",  "name": "observationCardinality","type": "uint16"},
            {"internalType": "uint16",  "name": "observationCardinalityNext","type": "uint16"},
            {"internalType": "bool",    "name": "unlocked",        "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ── Математика Uniswap v3 ─────────────────────────────────────────────────────

def tick_to_price(tick: int, token0_decimals: int = 18, token1_decimals: int = 6) -> float:
    """
    Цена token1 в единицах token0.
    Для WETH(18)/USDC(6): tick → цена ETH в USDC.
    """
    raw = 1.0001 ** tick
    adjusted = raw * (10 ** token0_decimals) / (10 ** token1_decimals)
    # WETH=token0, USDC=token1 → price = USDC per WETH
    return adjusted


def liquidity_to_amounts(
    liquidity: int,
    sqrt_price_x96: int,
    tick_lower: int,
    tick_upper: int,
    token0_decimals: int = 18,
    token1_decimals: int = 6,
) -> tuple[float, float]:
    """
    Рассчитывает реальные amount0/amount1 из liquidity.
    """
    Q96 = 2**96
    sqrt_price = sqrt_price_x96 / Q96

    sqrt_lower = math.sqrt(1.0001 ** tick_lower)
    sqrt_upper = math.sqrt(1.0001 ** tick_upper)

    current_tick_approx = math.log(sqrt_price ** 2) / math.log(1.0001)

    if current_tick_approx <= tick_lower:
        # Вся ликвидность в token0
        amount0 = liquidity * (1 / sqrt_lower - 1 / sqrt_upper)
        amount1 = 0.0
    elif current_tick_approx >= tick_upper:
        # Вся ликвидность в token1
        amount0 = 0.0
        amount1 = liquidity * (sqrt_upper - sqrt_lower)
    else:
        amount0 = liquidity * (1 / sqrt_price - 1 / sqrt_upper)
        amount1 = liquidity * (sqrt_price - sqrt_lower)

    amount0 /= 10 ** token0_decimals
    amount1 /= 10 ** token1_decimals
    return amount0, amount1


# ── Основная логика ───────────────────────────────────────────────────────────

def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌  Не удалось подключиться к Base RPC")
        return

    print(f"✅  Подключено к Base, блок #{w3.eth.block_number}\n")
    print(f"👛  Кошелёк: {WALLET}\n")

    # 1. Ищем Gauge со стейком
    gauge = None
    token_ids = []

    for candidate in GAUGE_CANDIDATES:
        c = w3.eth.contract(address=candidate, abi=GAUGE_ABI)
        try:
            ids = c.functions.stakedValues(WALLET).call()
            if ids:
                gauge = c
                token_ids = ids
                print(f"📍  Gauge найден: {candidate}")
                print(f"🪙  Застейканные tokenId: {token_ids}\n")
                break
            else:
                print(f"⚪  Gauge {candidate}: нет позиций")
        except Exception as e:
            print(f"⚠️   Gauge {candidate}: ошибка — {e}")

    if not gauge:
        print("❌  Gauge не найден. Проверь адреса GAUGE_CANDIDATES.")
        return

    # 2. slot0 пула
    pool = w3.eth.contract(address=POOL_ADDRESS, abi=POOL_ABI)
    slot0 = pool.functions.slot0().call()
    sqrt_price_x96 = slot0[0]
    current_tick   = slot0[1]

    eth_price_usdc = tick_to_price(current_tick)
    print(f"📊  Текущий tick: {current_tick}")
    print(f"💲  ETH цена: ${eth_price_usdc:,.2f}\n")

    # 3. Каждая позиция
    npm = w3.eth.contract(address=NPM_ADDRESS, abi=NPM_ABI)

    for token_id in token_ids:
        print(f"─── Позиция #{token_id} ───────────────────────────────")
        pos = npm.functions.positions(token_id).call()

        tick_lower  = pos[5]
        tick_upper  = pos[6]
        liquidity   = pos[7]

        price_lower = tick_to_price(tick_lower)
        price_upper = tick_to_price(tick_upper)

        in_range = tick_lower <= current_tick <= tick_upper

        amount0, amount1 = liquidity_to_amounts(
            liquidity, sqrt_price_x96, tick_lower, tick_upper
        )

        total_usd = amount0 * eth_price_usdc + amount1

        print(f"  Liquidity : {liquidity}")
        print(f"  Диапазон  : ${price_lower:,.2f} — ${price_upper:,.2f}")
        print(f"  В диапазоне: {'✅ ДА' if in_range else '❌ НЕТ (вне диапазона)'}")
        print(f"  WETH      : {amount0:.6f} ETH  (≈${amount0 * eth_price_usdc:,.2f})")
        print(f"  USDC      : {amount1:,.2f} USDC")
        print(f"  Итого USD : ≈${total_usd:,.2f}")

        # 4. Награды AERO
        try:
            earned_raw = gauge.functions.earned(AERO_ADDRESS, token_id).call()
            earned_aero = earned_raw / 1e18
            print(f"  AERO награды: {earned_aero:.4f} AERO")
        except Exception as e:
            print(f"  AERO награды: ошибка — {e}")

        print()

    # 5. Баланс AERO в кошельке
    aero = w3.eth.contract(address=AERO_ADDRESS, abi=ERC20_ABI)
    aero_balance = aero.functions.balanceOf(WALLET).call() / 1e18
    print(f"💰  AERO в кошельке: {aero_balance:.4f} AERO")


if __name__ == "__main__":
    main()
