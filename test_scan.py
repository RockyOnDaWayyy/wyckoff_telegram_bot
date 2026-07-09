import asyncio
import sys
import os
import logging

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)

import telegram_bot
import data_fetcher

async def test_scan_subset():
    print("=" * 60)
    print("CHẠY THỬ QUÉT THỊ TRƯỜNG HOSE (SUBSET)")
    print("=" * 60)
    
    # Temporarily monkey patch get_hose_tickers to only return a subset for quick testing
    original_get_tickers = data_fetcher.get_hose_tickers
    
    # Test with a subset of 10 major tickers to make it fast
    test_tickers = ["HPG", "SSI", "VCB", "FPT", "MWG", "VHM", "VIC", "VNM", "TCB", "CTG"]
    data_fetcher.get_hose_tickers = lambda: test_tickers
    
    print(f"Quét thử nghiệm với các mã: {test_tickers}")
    
    # Run the scan job
    await telegram_bot.run_market_scan_job(None)
    
    # Restore original function
    data_fetcher.get_hose_tickers = original_get_tickers
    
    # Read the cache to check if saved correctly
    cache = telegram_bot.load_cache()
    if cache:
        print("\n" + "=" * 40)
        print("KẾT QUẢ QUÉT ĐÃ LƯU TRONG CACHE:")
        print("=" * 40)
        print(f"Ngày quét: {cache.get('date')}")
        recs = cache.get('recommendations', [])
        print(f"Số lượng mã được khuyến nghị: {len(recs)}")
        for i, rec in enumerate(recs, 1):
            print(f"{i}. {rec['symbol']}: Giá {rec['price']:,.0f} VND - Pha: {rec['phase']} - RS: {rec['rs_status']}")
            print(f"   Tín hiệu: {rec['desc']}")
        print("=" * 60)
    else:
        print("Lỗi: Không tìm thấy cache quét thị trường.")

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(test_scan_subset())
