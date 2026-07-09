import sys
import os
import pandas as pd
import datetime

# Configure stdout to use UTF-8 for Windows terminal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import data_fetcher
import wyckoff_analyzer
import chart_generator

def test_single_stock(symbol):
    print("=" * 60)
    print(f"BẮT ĐẦU CHẠY THỬ PHÂN TÍCH CHO MÃ: {symbol}")
    print("=" * 60)
    
    # 1. Fetch data
    print("1. Tải dữ liệu lịch sử...")
    df = data_fetcher.get_historical_data(symbol)
    if df.empty:
        print(f"Lỗi: Không tải được dữ liệu cho mã {symbol}")
        return
        
    print(f"Đã tải {len(df)} dòng dữ liệu từ {df['Date'].min()} đến {df['Date'].max()}")
    
    # 2. Process Indicators
    print("2. Tính toán các chỉ báo kỹ thuật VSA...")
    df = wyckoff_analyzer.calculate_indicators(df)
    
    # 3. Wyckoff Analysis
    print("3. Phân tích cấu trúc pha Wyckoff...")
    analysis = wyckoff_analyzer.detect_wyckoff_structure(df)
    
    # Latest VSA bar
    latest_pattern = None
    latest_desc = ""
    if len(df) >= 3:
        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        prev_row2 = df.iloc[-3]
        latest_pattern, latest_desc = wyckoff_analyzer.detect_vsa_bar(row, prev_row, prev_row2)
        
    # Relative Strength
    print("4. So sánh sức mạnh tương đối với VNINDEX...")
    vnindex_df = data_fetcher.get_historical_data("VNINDEX")
    if not vnindex_df.empty:
        vnindex_df = wyckoff_analyzer.calculate_indicators(vnindex_df)
        rs_info = wyckoff_analyzer.analyze_relative_strength(df, vnindex_df)
    else:
        rs_info = {"status": "Neutral", "desc": "Không có dữ liệu VNINDEX"}

    # 4. Quantitative metrics
    print("5. Tính toán các chỉ số định lượng (VaR, MDD)...")
    quant = wyckoff_analyzer.calculate_quant_metrics(df)
    
    # 5. Plot Chart
    print("6. Vẽ biểu đồ phân tích Wyckoff...")
    chart_path = chart_generator.plot_wyckoff_chart(df, analysis, symbol)
    if chart_path:
        print(f"Biểu đồ đã được lưu tại: {chart_path}")
    else:
        print("Lỗi: Không vẽ được biểu đồ.")
        
    # 6. Print Report Summary
    print("\n" + "=" * 40)
    print("KẾT QUẢ BÁO CÁO TÓM TẮT:")
    print("=" * 40)
    print(f"Mã cổ phiếu: {symbol}")
    print(f"Giá đóng cửa gần nhất: {df.iloc[-1]['Close']:,.0f} VND ({df.iloc[-1]['Return']*100:+.2f}%)")
    print(f"Pha Wyckoff hiện tại: {analysis['phase']}")
    print(f"Mô tả pha: {analysis['phase_desc']}")
    print(f"Đường Hỗ trợ: {analysis['support']:,.0f} VND")
    print(f"Đường Kháng cự: {analysis['resistance']:,.0f} VND")
    print(f"Tín hiệu VSA nến cuối: {latest_pattern if latest_pattern else 'Bình thường'} - {latest_desc}")
    print(f"Sức mạnh tương quan: {rs_info['status']} - {rs_info['desc']}")
    print(f"Tỉ lệ thắng (Win Rate 1 tháng): {quant['win_rate']:.1f}%")
    print(f"Hiệu suất ROI trung bình (1 tháng): {quant['avg_roi']:+.1f}%")
    print(f"Tỷ lệ Risk/Reward thực tế: {quant['rr_ratio']:.1f}:1")
    print(f"VaR 95% (1 tháng): {quant['var_95']:.1f}%")
    print(f"Sụt giảm tối đa 1 năm (MDD): {quant['mdd']:.1f}%")
    
    print("\n" + "=" * 40)
    print("KHUYẾN NGHỊ PHÂN BỔ VÀ QUẢN TRỊ RỦI RO CHI TIẾT:")
    print("=" * 40)
    recs = wyckoff_analyzer.generate_wyckoff_recommendations(df, analysis, latest_pattern)
    clean_recs = recs.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
    print(clean_recs)
    
    print("\nCác tín hiệu cấu trúc Wyckoff phát hiện trong 120 phiên gần nhất:")
    for sig in analysis['signals']:
        print(f" - Ngày {sig['date'].strftime('%Y-%m-%d')}: {sig['label']} tại giá {sig['price']:,.0f} -> {sig['desc']}")
        
    print("=" * 60)

if __name__ == "__main__":
    test_single_stock("FPT")
