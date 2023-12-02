from aiogram import Bot, Dispatcher, executor, types
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from binance.client import Client
from ta.momentum import RSIIndicator
import pandas as pd
import matplotlib.pyplot as plt
import os
import logging

# Ваши данные для входа в Binance API
api_key = 'UO04Q1CqkMCVadizZ5ipbGwBCx7UhpDCeFrBBm3Z9VJfRHEssY6Y6fDLlfhuZuS3'
api_secret = 'zjiXpZKVBmNPhgp0LHzQbDoJkausYyFY23lH3WFNZSLYySCpgp2YTSeSl0vhmba0'

bot = Bot('6952968786:AAHrWs3kqR8fb08tk4TfoSL4T1aGN4tK97Y')
dp = Dispatcher(bot=bot)


keyboard_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
# кнопка, каждая из которых представляется экземпляром класса KeyboardButton
button = types.KeyboardButton('analyze')
keyboard_markup.add(button)

client = Client(api_key, api_secret)

down = 0
up = 1
stable = 2

@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message):
    await message.reply("Привет!", reply_markup=keyboard_markup)
  

async def send_message(chat_id, message):
    await bot.send_message(chat_id, message)

@dp.message_handler(text='analyze')
async def analyze(message: types.Message):
   # Анализируем все пары на Binance
    info = client.get_ticker()
    info.sort(key=lambda x: float(x['volume']), reverse=True)
    top_500_symbols = info[:500]
    for symbol in top_500_symbols:
        data = get_data(symbol['symbol'])
        rsi_data = calculate_rsi(data, symbol['symbol'])
        if rsi_data is not None:
            rsi_move, f_rsi, s_rsi = rsi_data
        else:
            continue
        price_move, first, second = calculate_move_price(data)
        divergence = check_divergence(rsi_move, price_move, f_rsi, s_rsi, first, second)
        if divergence != None:
            await send_message(chat_id=message.chat.id, message=f"{divergence} \nна {symbol['symbol']}")

            average_price = data['close'].rolling(7).mean()
            average_rsi = data['rsi'].rolling(7).mean()

            # Создаем новый график
            fig, ax1 = plt.subplots(figsize=(10, 5))

            # Рисуем цену активов
            color = 'tab:blue'
            ax1.set_xlabel('Time')
            ax1.set_ylabel('Price', color=color)
            ax1.plot(data['close'], color=color, label='Close Price')
            ax1.plot(average_price, color='green', label='Average Price')
            ax1.tick_params(axis='y', labelcolor=color)

            # Создаем вторую ось Y для RSI
            ax2 = ax1.twinx()
            color = 'tab:red'
            ax2.set_ylabel('RSI', color=color)
            ax2.plot(data['rsi'], color=color, label='RSI')
            ax2.plot(average_rsi, color='purple', label='Average RSI')
            ax2.tick_params(axis='y', labelcolor=color)

            fig.tight_layout()
            plt.title(f"{divergence} on {symbol['symbol']}")
            fig.legend(loc="upper left")

            # Сохраняем график в папку "media" в текущей директории
            if not os.path.exists('media'):
                os.makedirs('media')
            plt.savefig(f'media/{symbol["symbol"]}_divergence.png')
            plt.close()

            # Отправляем график пользователю
            await bot.send_photo(chat_id=message.chat.id, photo=open(f'media/{symbol["symbol"]}_divergence.png', 'rb'))
    else:
        await send_message(chat_id=message.chat.id, message="Анализ окончен")


def calculate_rsi(data: pd.DataFrame, symbol: str, period: int = 14):
    # Вычисляем RSI
    rsi_indicator = RSIIndicator(data['close'], period)
    data['rsi'] = rsi_indicator.rsi()
    f_rsi = data['rsi'].iloc[-14:-7].mean()
    s_rsi = data['rsi'].iloc[-7:].mean()
    if pd.isna(f_rsi) or pd.isna(s_rsi):
        print(f"{symbol} RSI values are NaN, skipping analysis")
        return None

    if f_rsi < s_rsi:
        return down, f_rsi, s_rsi
    elif f_rsi > s_rsi:
        return up, f_rsi, s_rsi
    elif f_rsi == s_rsi:
        return stable, f_rsi, s_rsi
    else:
        print('WHAT?')
        

def calculate_move_price(data: pd.DataFrame):
    # Вычисляем максимумы и движение цены
    first = data['close'].iloc[-14:-7].mean()
    second = data['close'].iloc[-7:].mean()
    if first < second:
        return down, first, second
    elif first > second:
        return up, first, second
    elif first == second:
        return stable, first, second
    else:
        print('ТАКОЕ ВОЗМОЖНО?')
    

def check_divergence(price_move, rsi_move, f_rsi, s_rsi, first, second):
    # Проверяем на дивергенцию
    if price_move == down and rsi_move == up:
        return f'Медвежья обратная класса А\nBUY\n{f_rsi}, s_rsi: {s_rsi}, first: {first}, second: {second},\n {rsi_move}\n{price_move}'
    elif price_move == up and rsi_move == down:
        return f'Медвежья прямая класса А\nSELL\n{f_rsi}, s_rsi: {s_rsi}, first: {first}, second: {second},\n {rsi_move}\n{price_move}'
    elif price_move == stable and rsi_move == down:
        return f'Медвежья прямая класса Б,\n SELL\n{f_rsi}, s_rsi: {s_rsi}, first: {first}, second: {second},\n {rsi_move}\n{price_move}'
    elif price_move == stable and rsi_move == up:
        return f'Медвежья обратная класса Б,\n BUY\n{f_rsi}, s_rsi: {s_rsi}, first: {first}, second: {second},\n {rsi_move}\n{price_move}'
    elif price_move == up and rsi_move == up or price_move == down and rsi_move == down:
        return None
    else:
        print('тут пусто')


def get_data(symbol: str, interval: str = Client.KLINE_INTERVAL_1DAY, limit: int = 30):
    # Получаем данные с Binance за последний месяц
    candles = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    data = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    data['close'] = pd.to_numeric(data['close'])
    
    # Преобразуем столбец 'time' в формат datetime и устанавливаем его в качестве индекса
    data['time'] = pd.to_datetime(data['time'], unit='ms')
    data.set_index('time', inplace=True)
    
    return data

if __name__ == '__main__':
    executor.start_polling(dp)