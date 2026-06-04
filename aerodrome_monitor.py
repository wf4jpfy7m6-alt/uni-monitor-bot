"""
aerodrome_monitor.py
Мониторинг застейканной позиции Aerodrome (Base) WETH/USDC через NPM и Gauge.
"""

import math
import asyncio
from web3 import Web3

# ── Конфигурация контрактов ───────────────────────────────────────────────────
RPC_URL = "https://mainnet.base.org"
NPM_ADDRESS = Web3.to_checksum_address("0x827922686190790b37229fd06084350E74485b72")
POOL_ADDRESS = Web3.to_checksum_address("0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59")

# ── ABI контрактов ────────────────────────────────────────────────────────────
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
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "uint256", "name": "index", "type": "uint256"}
        ],
        "name": "tokenOfOwnerByIndex",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
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

# ── Математические функции ────────────────────────────────────────────────────
def tick_to_price(tick: int, token0_decimals: int = 18, token1_decimals: int = 6) -> float:
    try:
        raw = 1.0001 ** tick
        return raw * (10 ** token0_decimals) / (10 ** token1_decimals)
    except Exception:
        return 0.0

def liquidity_to_amounts(liquidity: int, sqrt_price_x96: int, tick_lower: int, tick_upper: int) -> tuple[float, float]:
    try:
        Q96 = 2**96
        sqrt_price = sqrt_price_x96 / Q96
        sqrt_lower = math.sqrt(1.0001 ** tick_lower)
        sqrt_upper = math.sqrt(1.0001 ** tick_upper)
        current_tick_approx = math.log(sqrt_price ** 2) / math.log(1.0001)

        if current_tick_approx <= tick_lower:
            amount0 = liquidity * (1 / sqrt_lower - 1 / sqrt_upper)
            amount1 = 0.0
        elif current_tick_approx >= tick_upper:
            amount0 = 0.0
            amount1 = liquidity * (sqrt_upper - sqrt_lower)
        else:
            amount0 = liquidity * (1 / sqrt_price - 1 / sqrt_upper)
            amount1 = liquidity * (sqrt_price - sqrt_lower)

        return amount0 / 1e18, amount1 / 1e6
    except Exception:
        return 0.0, 0.0


# ── Класс Монитора ────────────────────────────────────────────────────────────
class AerodromeMonitor:
    def __init__(self, wallet_address: str, gauge_address: str):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        self.wallet = Web3.to_checksum_address(wallet_address)
        self.gauge_address = Web3.to_checksum_address(gauge_address)
        
        self.pool_contract = self.w3.eth.contract(address=POOL_ADDRESS, abi=POOL_ABI)
        self.npm_contract = self.w3.eth.contract(address=NPM_ADDRESS, abi=NPM_ABI)

    async def get_positions(self) -> list:
        return await asyncio.to_thread(self._get_positions_sync)

    def _get_positions_sync(self) -> list:
        if not self.w3.is_connected():
            return []

        token_ids = []
        
        # 1. Сканируем NFT на самом кошельке кошельке
        try:
            balance = self.npm_contract.functions.balanceOf(self.wallet).call()
            for i in range(balance):
                t_id = self.npm_contract.functions.tokenOfOwnerByIndex(self.wallet, i).call()
                token_ids.append(t_id)
        except Exception as e:
            print(f"⚠️ Ошибка проверки баланса кошелька: {e}")

        # 2. Сканируем NFT, застейканные внутри контракта Gauge
        try:
            gauge_balance = self.npm_contract.functions.balanceOf(self.gauge_address).call()
            for i in range(gauge_balance):
                t_id = self.npm_contract.functions.tokenOfOwnerByIndex(self.gauge_address, i).call()
                token_ids.append(t_id)
        except Exception as e:
            print(f"⚠️ Ошибка проверки баланса Gauge контракта: {e}")

        # Удаляем дубликаты, если они возникли
        token_ids = list(set(token_ids))

        if not token_ids:
            return []

        try:
            slot0 = self.pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            current_tick = slot0[1]
            eth_price_usdc = tick_to_price(current_tick)
        except Exception as e:
            print(f"🚨 Ошибка получения slot0 пула: {e}")
            return []

        parsed_positions = []

        for token_id in token_ids:
            try:
                pos = self.npm_contract.functions.positions(token_id).call()
                
                # Защита: Сверяем, что это наш пул WETH/USDC
                t0 = pos[2].lower()
                t1 = pos[3].lower()
                weth_check = "0x4200000000000000000000000000000000000006".lower()
                usdc_check = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913".lower()
                
                if not ((t0 == weth_check and t1 == usdc_check) or (t0 == usdc_check and t1 == weth_check)):
                    continue  # Пропускаем сторонние NFT, если они есть

                tick_lower = pos[5]
                tick_upper = pos[6]
                liquidity = pos[7]

                price_lower = tick_to_price(tick_lower)
                price_upper = tick_to_price(tick_upper)
                in_range = tick_lower <= current_tick <= tick_upper

                amount0, amount1 = liquidity_to_amounts(
                    liquidity, sqrt_price_x96, tick_lower, tick_upper
                )
                total_usd = amount0 * eth_price_usdc + amount1

                parsed_positions.append({
                    "network": "Base (Aerodrome)",
                    "token_id": token_id,
                    "token0": "WETH",
                    "token1": "USDC",
                    "price_lower": price_lower,
                    "price_upper": price_upper,
                    "current_price": eth_price_usdc,
                    "in_range": in_range,
                    "value_usd": total_usd
                })
            except Exception as e:
                # Теперь битые или старые ID просто безопасно пропускаются мимо
                print(f"⚠️ Пропущен неактивный ID #{token_id}: {e}")
                continue

        return parsed_positions
