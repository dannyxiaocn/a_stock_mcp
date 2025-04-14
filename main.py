# server.py
from mcp.server.fastmcp import FastMCP
import akshare as ak
import pandas as pd
import mplfinance as mpf
import datetime

import os
import matplotlib.pyplot as plt
import tempfile

# Create an MCP server
mcp = FastMCP("A股分析助手", dependencies=["akshare", "openai", "mplfinance", "matplotlib"])

@mcp.tool()
def get_one_stock_financial_data(symbol_em: str) -> str:
    """
    使用AKShare接口获取个股财务数据，并计算关键财务指标
    @param symbol_em: 东方财富股票代码(如："600519")
    """
    result_sections = []
    
    # 1. 获取东方财富股票基本信息
    try:
        stock_info_em_df = ak.stock_individual_info_em(symbol=symbol_em, timeout=5)
        result_sections.append("== 股票基本信息(东方财富) ==")
        result_sections.append(stock_info_em_df.to_string())
        # 转换为字典，方便后续处理
        stock_info_dict = dict(zip(stock_info_em_df['item'], stock_info_em_df['value']))
    except Exception as e:
        result_sections.append(f"获取东方财富股票信息失败")
        stock_info_dict = {}
    
    # 2. 获取雪球股票基本信息
    try:
        # 构建雪球代码，需要在前面加上交易所标志
        exchange_prefix = "SH" if symbol_em.startswith(("6", "9")) else "SZ"
        symbol_xq = f"{exchange_prefix}{symbol_em}"
        stock_info_xq_df = ak.stock_individual_basic_info_xq(symbol=symbol_xq, timeout=5)
        result_sections.append("\n== 公司概况(雪球) ==")
        # 选取重要信息
        important_fields = ['org_name_cn', 'main_operation_business', 'established_date', 
                           'staff_num', 'reg_asset', 'industry', 'classi_name']
        if not stock_info_xq_df.empty:
            filtered_info = stock_info_xq_df[stock_info_xq_df['item'].isin(important_fields)]
            result_sections.append(filtered_info.to_string())
    except Exception as e:
        result_sections.append(f"\n获取雪球股票信息失败")
    
    # 3. 获取实时行情与盘口数据
    try:
        stock_bid_ask_df = ak.stock_bid_ask_em(symbol=symbol_em)
        result_sections.append("\n== 实时盘口数据 ==")
        result_sections.append(stock_bid_ask_df.to_string())
        
        # 提取关键指标用于后续分析
        bid_ask_dict = dict(zip(stock_bid_ask_df['item'], stock_bid_ask_df['value']))
    except Exception as e:
        result_sections.append(f"\n获取盘口数据失败")
        bid_ask_dict = {}
    
    # 4. 获取历史行情数据(近90天)
    try:
        end_date = datetime.datetime.now().strftime('%Y%m%d')
        start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime('%Y%m%d')
        
        hist_data_df = ak.stock_zh_a_hist(symbol=symbol_em, period="daily", 
                                          start_date=start_date, end_date=end_date, 
                                          adjust="qfq")
        
        result_sections.append("\n== 历史行情数据概览(近90天) ==")
        result_sections.append(f"数据周期: {start_date} 至 {end_date}")
        result_sections.append(f"交易日数量: {len(hist_data_df)}")
        if not hist_data_df.empty:
            latest = hist_data_df.iloc[-1]
            earliest = hist_data_df.iloc[0]
            result_sections.append(f"区间首日价格: {earliest['收盘']:.2f}元")
            result_sections.append(f"区间末日价格: {latest['收盘']:.2f}元")
            price_change = (latest['收盘'] - earliest['收盘']) / earliest['收盘'] * 100
            result_sections.append(f"区间涨跌幅: {price_change:.2f}%")
    except Exception as e:
        result_sections.append(f"\n获取历史行情数据失败")
        hist_data_df = None
    
    # 5. 财务分析
    result_sections.append("\n== 财务分析 ==")
    
    # 5.1 市场估值分析
    try:
        if 'stock_info_dict' in locals() and stock_info_dict:
            pe_info = stock_info_em_df[stock_info_em_df['item'] == '市盈率']
            if not pe_info.empty:
                pe_ratio = pe_info['value'].values[0]
                result_sections.append(f"市盈率(PE): {pe_ratio}")
                
                # 估值分析
                if pe_ratio < 15:
                    pe_analysis = "低估值，可能具有投资价值"
                elif 15 <= pe_ratio < 30:
                    pe_analysis = "中等估值，价格较为合理"
                else:
                    pe_analysis = "高估值，需谨慎投资"
                result_sections.append(f"估值分析: {pe_analysis}")
        
        # 从盘口数据提取更多指标
        if bid_ask_dict:
            if '量比' in bid_ask_dict:
                volume_ratio = bid_ask_dict['量比']
                result_sections.append(f"量比: {volume_ratio:.2f}")
                if volume_ratio > 1.5:
                    vol_analysis = "成交活跃度高于平均水平"
                else:
                    vol_analysis = "成交活跃度低于平均水平"
                result_sections.append(f"成交活跃度分析: {vol_analysis}")
            
            if '换手率' in bid_ask_dict:
                turnover_rate = bid_ask_dict['换手率']
                result_sections.append(f"换手率: {turnover_rate:.2f}%")
                if turnover_rate > 3:
                    turnover_analysis = "市场交投活跃"
                else:
                    turnover_analysis = "市场交投较为平静"
                result_sections.append(f"市场活跃度分析: {turnover_analysis}")
    except Exception as e:
        result_sections.append(f"市场估值分析失败")
    
    # 5.2 技术指标分析
    try:
        if hist_data_df is not None and not hist_data_df.empty:
            # 计算20日均线
            hist_data_df['MA20'] = hist_data_df['收盘'].rolling(window=20).mean()
            
            # 获取最新交易日数据
            latest_day = hist_data_df.iloc[-1]
            latest_close = latest_day['收盘']
            latest_ma20 = latest_day['MA20'] if not pd.isna(latest_day['MA20']) else None
            
            result_sections.append("\n技术指标分析:")
            if latest_ma20 is not None:
                diff_pct = (latest_close - latest_ma20) / latest_ma20 * 100
                result_sections.append(f"最新收盘价: {latest_close:.2f}元")
                result_sections.append(f"20日均线: {latest_ma20:.2f}元")
                result_sections.append(f"乖离率(收盘价相对20日均线): {diff_pct:.2f}%")
                
                if latest_close > latest_ma20:
                    tech_analysis = "股价站上20日均线，短期走势偏强"
                else:
                    tech_analysis = "股价位于20日均线下方，短期走势偏弱"
                result_sections.append(tech_analysis)
            
            # 计算近期波动率
            if len(hist_data_df) >= 20:
                recent_volatility = hist_data_df['涨跌幅'].tail(20).std()
                result_sections.append(f"近20交易日波动率: {recent_volatility:.2f}%")
                
                if recent_volatility > 3:
                    vol_analysis = "波动较大，风险较高"
                else:
                    vol_analysis = "波动较小，相对稳定"
                result_sections.append(vol_analysis)
    except Exception as e:
        result_sections.append(f"技术指标分析失败")
    
    # 5.3 总体财务评估
    try:
        result_sections.append("\n总体财务评估:")
        
        # 基于之前分析的综合评估
        strengths = []
        weaknesses = []
        
        # 根据之前的分析添加优势和劣势
        if 'stock_info_dict' in locals() and stock_info_dict:
            pe_info = stock_info_em_df[stock_info_em_df['item'] == '市盈率']
            if not pe_info.empty:
                pe_ratio = pe_info['value'].values[0]
                if pe_ratio < 15:
                    strengths.append("低估值")
                elif pe_ratio > 30:
                    weaknesses.append("高估值")
        
        if bid_ask_dict and '量比' in bid_ask_dict and bid_ask_dict['量比'] > 1.5:
            strengths.append("成交活跃")
        
        if hist_data_df is not None and not hist_data_df.empty:
            latest_day = hist_data_df.iloc[-1]
            earliest_day = hist_data_df.iloc[0]
            price_change = (latest_day['收盘'] - earliest_day['收盘']) / earliest_day['收盘'] * 100
            
            if price_change > 10:
                strengths.append("近期走势强劲")
            elif price_change < -10:
                weaknesses.append("近期走势疲软")
        
        if strengths:
            result_sections.append(f"优势: {', '.join(strengths)}")
        if weaknesses:
            result_sections.append(f"劣势: {', '.join(weaknesses)}")
        
        # 简单投资建议
        if len(strengths) > len(weaknesses):
            result_sections.append("初步投资建议: 可考虑关注")
        elif len(strengths) < len(weaknesses):
            result_sections.append("初步投资建议: 建议谨慎")
        else:
            result_sections.append("初步投资建议: 中性观望")
        
        result_sections.append("\n【免责声明】以上分析仅供参考，不构成投资建议。投资决策需结合个人风险偏好和更全面的信息。")
    except Exception as e:
        result_sections.append(f"总体财务评估失败")
    
    # 6. 深入财务指标分析（整合自calculate_key_financial_indicators）
    result_sections.append("\n=========== 深入财务指标分析 ===========")
    
    # 6.1 获取年度历史数据（如果之前的历史数据不足1年）
    try:
        # 重新获取一年的历史数据，用于计算年化指标
        if hist_data_df is None or len(hist_data_df) < 250:
            end_date = datetime.datetime.now().strftime('%Y%m%d')
            start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y%m%d')
            
            annual_hist_data_df = ak.stock_zh_a_hist(symbol=symbol_em, period="daily", 
                                                  start_date=start_date, end_date=end_date, 
                                                  adjust="qfq")
        else:
            annual_hist_data_df = hist_data_df
    except Exception as e:
        result_sections.append(f"获取年度历史数据失败: {str(e)}")
        annual_hist_data_df = hist_data_df
    
    # 6.2 深入盈利能力指标分析
    result_sections.append("\n== 盈利能力指标分析 ==")
    
    if stock_info_dict:
        # 详细市盈率(PE)分析
        if '市盈率' in stock_info_dict:
            pe_ratio = stock_info_dict['市盈率']
            # 市盈率分析
            try:
                pe_float = float(pe_ratio)
                if pe_float < 0:
                    pe_analysis = "负值，可能表明公司当前处于亏损状态"
                elif pe_float < 15:
                    pe_analysis = "较低，可能被低估或存在风险因素"
                elif 15 <= pe_float < 30:
                    pe_analysis = "处于合理区间，符合行业平均水平"
                elif 30 <= pe_float < 50:
                    pe_analysis = "较高，投资者对公司未来增长预期较强"
                else:
                    pe_analysis = "极高，可能存在泡沫或特殊增长预期"
                result_sections.append(f"市盈率深入分析: {pe_analysis}")
            except:
                result_sections.append("市盈率分析失败，可能为非数值")
        
        # 市净率(PB)详细分析
        if '市净率' in stock_info_dict:
            pb_ratio = stock_info_dict['市净率']
            # 市净率分析
            try:
                pb_float = float(pb_ratio)
                if pb_float < 1:
                    pb_analysis = "低于1，可能被低估或资产回报率较低"
                elif 1 <= pb_float < 3:
                    pb_analysis = "处于合理区间，符合一般企业估值水平"
                else:
                    pb_analysis = "较高，表明市场对公司资产质量评价较高"
                result_sections.append(f"市净率深入分析: {pb_analysis}")
            except:
                result_sections.append("市净率分析失败，可能为非数值")
    
    # 6.3 深入成长性指标分析
    result_sections.append("\n== 成长性指标深入分析 ==")
    
    if annual_hist_data_df is not None and not annual_hist_data_df.empty:
        # 计算年度涨跌幅
        if len(annual_hist_data_df) > 1:
            earliest_price = annual_hist_data_df.iloc[0]['收盘']
            latest_price = annual_hist_data_df.iloc[-1]['收盘']
            annual_return = (latest_price - earliest_price) / earliest_price * 100
            result_sections.append(f"年度涨跌幅: {annual_return:.2f}%")
            
            # 年度涨跌幅分析
            if annual_return > 30:
                return_analysis = "强劲增长，显著跑赢大盘"
            elif 10 <= annual_return <= 30:
                return_analysis = "良好增长，表现优于市场平均水平"
            elif 0 <= annual_return < 10:
                return_analysis = "小幅增长，基本符合市场表现"
            elif -10 <= annual_return < 0:
                return_analysis = "小幅下跌，略低于市场表现"
            else:
                return_analysis = "大幅下跌，表现不佳"
            result_sections.append(f"年度涨跌幅分析: {return_analysis}")
        
        # 计算波动率(年化标准差)
        if len(annual_hist_data_df) > 20:  # 至少需要20个交易日
            returns = annual_hist_data_df['涨跌幅'].dropna() / 100  # 转换为小数
            volatility = returns.std() * (252 ** 0.5)  # 年化波动率(假设一年252个交易日)
            result_sections.append(f"年化波动率: {volatility:.2f}%")
            
            # 波动率分析
            if volatility < 20:
                vol_analysis = "低波动性，价格相对稳定"
            elif 20 <= volatility < 30:
                vol_analysis = "中等波动性，符合行业平均水平"
            elif 30 <= volatility < 40:
                vol_analysis = "较高波动性，价格波动较大"
            else:
                vol_analysis = "高波动性，价格剧烈波动，风险较高"
            result_sections.append(f"波动率深入分析: {vol_analysis}")
            
        # 计算夏普比率(假设无风险利率为3%)
        if len(annual_hist_data_df) > 20 and 'returns' in locals() and 'volatility' in locals():
            risk_free_rate = 0.03  # 无风险利率，假设为3%
            avg_annual_return = returns.mean() * 252  # 年化平均收益率
            sharpe_ratio = (avg_annual_return - risk_free_rate) / volatility if volatility > 0 else 0
            result_sections.append(f"夏普比率: {sharpe_ratio:.2f}")
            
            # 夏普比率分析
            if sharpe_ratio < 0:
                sharpe_analysis = "负值，表明投资回报低于无风险利率"
            elif 0 <= sharpe_ratio < 0.5:
                sharpe_analysis = "较低，风险调整后回报不佳"
            elif 0.5 <= sharpe_ratio < 1:
                sharpe_analysis = "一般，风险和回报较为平衡"
            elif 1 <= sharpe_ratio < 2:
                sharpe_analysis = "良好，提供了较好的风险调整后回报"
            else:
                sharpe_analysis = "优秀，提供了极佳的风险调整后回报"
            result_sections.append(f"夏普比率分析: {sharpe_analysis}")
    
    # 6.4 深入流动性与交易指标分析
    result_sections.append("\n== 流动性与交易指标深入分析 ==")
    
    if bid_ask_dict:
        # 深入换手率分析
        if '换手率' in bid_ask_dict:
            turnover_rate = bid_ask_dict['换手率']
            
            # 换手率深入分析
            try:
                turnover_float = float(turnover_rate)
                if turnover_float < 1:
                    turnover_analysis = "低换手，交易不活跃，可能缺乏市场关注"
                elif 1 <= turnover_float < 3:
                    turnover_analysis = "正常换手，交易活跃度适中"
                elif 3 <= turnover_float < 7:
                    turnover_analysis = "高换手，交易较为活跃"
                else:
                    turnover_analysis = "极高换手，可能有重大事件或炒作"
                result_sections.append(f"换手率深入分析: {turnover_analysis}")
            except:
                result_sections.append("换手率分析失败，可能为非数值")
            
        # 深入量比分析
        if '量比' in bid_ask_dict:
            volume_ratio = bid_ask_dict['量比']
            
            # 量比深入分析
            try:
                vol_ratio_float = float(volume_ratio)
                if vol_ratio_float < 0.8:
                    vol_ratio_analysis = "低于0.8，成交低迷，人气不足"
                elif 0.8 <= vol_ratio_float < 1:
                    vol_ratio_analysis = "略低于1，成交量低于近期平均"
                elif 1 <= vol_ratio_float < 2:
                    vol_ratio_analysis = "处于正常范围，交易情况平稳"
                elif 2 <= vol_ratio_float < 3:
                    vol_ratio_analysis = "成交活跃，有大资金介入迹象"
                else:
                    vol_ratio_analysis = "成交异常活跃，可能有重大资金异动"
                result_sections.append(f"量比深入分析: {vol_ratio_analysis}")
            except:
                result_sections.append("量比分析失败，可能为非数值")
    
    # 6.5 深入技术指标分析
    result_sections.append("\n== 技术指标深入分析 ==")
    
    if annual_hist_data_df is not None and not annual_hist_data_df.empty:
        # 计算更多移动平均线
        if len(annual_hist_data_df) >= 20:
            annual_hist_data_df['MA5'] = annual_hist_data_df['收盘'].rolling(window=5).mean()
            annual_hist_data_df['MA10'] = annual_hist_data_df['收盘'].rolling(window=10).mean()
            annual_hist_data_df['MA20'] = annual_hist_data_df['收盘'].rolling(window=20).mean()
            if len(annual_hist_data_df) >= 60:
                annual_hist_data_df['MA60'] = annual_hist_data_df['收盘'].rolling(window=60).mean()
            
            # 获取最新交易日数据
            latest = annual_hist_data_df.iloc[-1]
            
            # 计算MACD
            annual_hist_data_df['EMA12'] = annual_hist_data_df['收盘'].ewm(span=12, adjust=False).mean()
            annual_hist_data_df['EMA26'] = annual_hist_data_df['收盘'].ewm(span=26, adjust=False).mean()
            annual_hist_data_df['DIF'] = annual_hist_data_df['EMA12'] - annual_hist_data_df['EMA26']
            annual_hist_data_df['DEA'] = annual_hist_data_df['DIF'].ewm(span=9, adjust=False).mean()
            annual_hist_data_df['MACD'] = 2 * (annual_hist_data_df['DIF'] - annual_hist_data_df['DEA'])
            
            latest_macd = annual_hist_data_df.iloc[-1]
            
            # 移动平均线深入分析
            result_sections.append(f"最新收盘价: {latest['收盘']:.2f}元")
            result_sections.append(f"5日均线: {latest['MA5']:.2f}元")
            result_sections.append(f"10日均线: {latest['MA10']:.2f}元")
            result_sections.append(f"20日均线: {latest['MA20']:.2f}元")
            
            if len(annual_hist_data_df) >= 60 and not pd.isna(latest['MA60']):
                result_sections.append(f"60日均线: {latest['MA60']:.2f}元")
            
            # 判断均线多空排列
            if not pd.isna(latest['MA5']) and not pd.isna(latest['MA10']) and not pd.isna(latest['MA20']):
                if latest['MA5'] > latest['MA10'] > latest['MA20']:
                    ma_trend = "多头排列，短期走势强劲"
                elif latest['MA5'] < latest['MA10'] < latest['MA20']:
                    ma_trend = "空头排列，短期走势疲软"
                else:
                    ma_trend = "均线交叉，趋势不明确"
                result_sections.append(f"均线排列: {ma_trend}")
            
            # MACD深入分析
            result_sections.append(f"MACD指标: DIF={latest_macd['DIF']:.4f}, DEA={latest_macd['DEA']:.4f}, MACD柱={latest_macd['MACD']:.4f}")
            
            if latest_macd['DIF'] > latest_macd['DEA']:
                if latest_macd['DIF'] > 0 and latest_macd['DEA'] > 0:
                    macd_signal = "MACD金叉且在零轴上方，强烈买入信号"
                elif latest_macd['DIF'] > 0 and latest_macd['DEA'] < 0:
                    macd_signal = "MACD金叉但仍在零轴下方，买入信号但需谨慎"
                else:
                    macd_signal = "MACD金叉但在零轴下方，弱买入信号"
            else:
                if latest_macd['DIF'] < 0 and latest_macd['DEA'] < 0:
                    macd_signal = "MACD死叉且在零轴下方，强烈卖出信号"
                elif latest_macd['DIF'] < 0 and latest_macd['DEA'] > 0:
                    macd_signal = "MACD死叉但仍在零轴上方，卖出信号但需谨慎"
                else:
                    macd_signal = "MACD死叉但在零轴上方，弱卖出信号"
            
            result_sections.append(f"MACD信号深入分析: {macd_signal}")
    
    # 6.6 估值指标市场对比分析
    result_sections.append("\n== 估值对比深入分析 ==")
    
    try:
        # 获取行业整体数据
        stock_sse_summary_df = ak.stock_sse_summary()
        if not stock_sse_summary_df.empty:
            market_pe = stock_sse_summary_df[stock_sse_summary_df['项目'] == '平均市盈率']
            if not market_pe.empty and '股票' in market_pe.columns:
                market_avg_pe = market_pe['股票'].values[0]
                result_sections.append(f"A股整体平均市盈率: {market_avg_pe}")
                
                # 与个股市盈率比较
                if '市盈率' in stock_info_dict:
                    try:
                        stock_pe = float(stock_info_dict['市盈率'])
                        market_pe_value = float(market_avg_pe)
                        pe_diff_pct = (stock_pe - market_pe_value) / market_pe_value * 100
                        
                        if pe_diff_pct < -20:
                            pe_compare = f"显著低于市场平均({pe_diff_pct:.2f}%)，可能被低估或存在风险因素"
                        elif -20 <= pe_diff_pct < 0:
                            pe_compare = f"略低于市场平均({pe_diff_pct:.2f}%)，估值相对合理"
                        elif 0 <= pe_diff_pct < 20:
                            pe_compare = f"略高于市场平均({pe_diff_pct:.2f}%)，估值相对合理"
                        else:
                            pe_compare = f"显著高于市场平均({pe_diff_pct:.2f}%)，可能存在高估风险"
                        
                        result_sections.append(f"市盈率市场对比: {pe_compare}")
                    except:
                        result_sections.append("市盈率对比分析失败，可能存在非数值数据")
    except Exception as e:
        result_sections.append(f"获取市场整体数据失败: {str(e)}")
    
    # 6.7 财务综合评分
    result_sections.append("\n== 财务综合评分 ==")
    
    # 综合各项指标评分
    score_items = []
    score_total = 0
    score_count = 0
    
    # 市盈率评分
    if '市盈率' in stock_info_dict:
        try:
            pe = float(stock_info_dict['市盈率'])
            if pe <= 0:  # 负PE意味着亏损
                pe_score = 0
            elif pe < 10:
                pe_score = 90  # 可能是价值股或有风险
            elif 10 <= pe < 20:
                pe_score = 80  # 合理估值
            elif 20 <= pe < 30:
                pe_score = 60  # 稍高估值
            elif 30 <= pe < 50:
                pe_score = 40  # 高估值
            else:
                pe_score = 20  # 极高估值
            
            score_items.append(f"市盈率评分: {pe_score} (PE={pe:.2f})")
            score_total += pe_score
            score_count += 1
        except:
            pass
    
    # 市净率评分
    if '市净率' in stock_info_dict:
        try:
            pb = float(stock_info_dict['市净率'])
            if pb < 1:
                pb_score = 85  # 低PB，可能被低估或资产效率低
            elif 1 <= pb < 2:
                pb_score = 80  # 合理PB
            elif 2 <= pb < 4:
                pb_score = 60  # 较高PB
            else:
                pb_score = 40  # 高PB
            
            score_items.append(f"市净率评分: {pb_score} (PB={pb:.2f})")
            score_total += pb_score
            score_count += 1
        except:
            pass
    
    # 技术面评分
    if 'ma_trend' in locals():
        if ma_trend == "多头排列，短期走势强劲":
            tech_score = 80
        elif ma_trend == "空头排列，短期走势疲软":
            tech_score = 40
        else:
            tech_score = 60
        
        score_items.append(f"技术面评分: {tech_score}")
        score_total += tech_score
        score_count += 1
    
    # MACD评分
    if 'macd_signal' in locals():
        if "强烈买入" in macd_signal:
            macd_score = 85
        elif "买入" in macd_signal:
            macd_score = 75
        elif "弱买入" in macd_signal:
            macd_score = 65
        elif "强烈卖出" in macd_signal:
            macd_score = 25
        elif "卖出" in macd_signal:
            macd_score = 35
        else:
            macd_score = 45
        
        score_items.append(f"MACD技术评分: {macd_score}")
        score_total += macd_score
        score_count += 1
    
    # 波动率评分
    if 'volatility' in locals():
        if volatility < 20:
            vol_score = 80  # 低波动，相对稳定
        elif 20 <= volatility < 30:
            vol_score = 70  # 中等波动
        elif 30 <= volatility < 40:
            vol_score = 50  # 较高波动
        else:
            vol_score = 30  # 高波动
        
        score_items.append(f"波动率评分: {vol_score} (波动率={volatility:.2f}%)")
        score_total += vol_score
        score_count += 1
    
    # 夏普比率评分
    if 'sharpe_ratio' in locals():
        if sharpe_ratio < 0:
            sharpe_score = 30
        elif 0 <= sharpe_ratio < 0.5:
            sharpe_score = 50
        elif 0.5 <= sharpe_ratio < 1:
            sharpe_score = 65
        elif 1 <= sharpe_ratio < 2:
            sharpe_score = 80
        else:
            sharpe_score = 90
        
        score_items.append(f"夏普比率评分: {sharpe_score} (夏普比率={sharpe_ratio:.2f})")
        score_total += sharpe_score
        score_count += 1
    
    # 输出各项得分
    for item in score_items:
        result_sections.append(item)
    
    # 计算总得分
    if score_count > 0:
        total_score = score_total / score_count
        result_sections.append(f"\n综合评分: {total_score:.1f}/100")
        
        # 投资建议
        if total_score >= 80:
            investment_advice = "优质投资标的，财务指标表现优秀"
        elif 70 <= total_score < 80:
            investment_advice = "良好投资标的，财务指标表现良好"
        elif 60 <= total_score < 70:
            investment_advice = "一般投资标的，财务指标表现中等"
        elif 50 <= total_score < 60:
            investment_advice = "谨慎投资，财务指标存在一定问题"
        else:
            investment_advice = "不建议投资，财务指标表现较差"
        
        result_sections.append(f"投资建议: {investment_advice}")
    
    # 最终免责声明
    result_sections.append("\n【免责声明】以上分析仅供参考，不构成投资建议。投资决策需结合个人风险偏好、市场情况和更全面的信息。")
    
    # 合并所有结果
    return "\n".join(result_sections)

@mcp.tool()
def track_stock_trend(symbol: str, period: str = "daily", days: int = 15) -> str:
    """
    跟踪股价走势，并利用 mplfinance 制作 K线图并保存
    @param symbol: 股票代码，如: "600519"
    @param period: 数据周期，可选 "daily", "weekly", "monthly"
    @param days: 获取历史数据的天数
    @return: 图表文件保存路径及基本统计信息
    """
    
    # 解决中文显示问题
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans', 'Bitstream Vera Sans', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    
    # 使用用户主目录下的临时目录保存图表，避免权限问题
    home_dir = os.path.expanduser("~")
    output_dir = os.path.join(home_dir, "stock_charts")
    
    # 创建图表保存目录
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        # 如果无法在主目录创建，则使用系统临时目录
        output_dir = os.path.join(tempfile.gettempdir(), "stock_charts")
        os.makedirs(output_dir, exist_ok=True)
    
    # 计算日期区间 - 延长时间范围确保有足够数据
    end_date = datetime.datetime.now().strftime('%Y%m%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=max(days, 90))).strftime('%Y%m%d')
    
    try:
        # 获取股票历史数据 
        stock_data = ak.stock_zh_a_hist(symbol=symbol, period=period, 
                                        start_date=start_date, 
                                        end_date=end_date, 
                                        adjust="qfq")
        
        if stock_data.empty or len(stock_data) < 2:
            return f"未获取到足够的股票 {symbol} 历史数据，请确认股票代码是否正确或尝试更长的时间范围"
        
        # 准备数据格式用于 mplfinance
        df = stock_data.copy()
        df = df.rename(columns={
            '日期': 'Date',
            '开盘': 'Open',
            '最高': 'High',
            '最低': 'Low',
            '收盘': 'Close',
            '成交量': 'Volume'
        })
        
        # 检查是否所有必要的列都存在
        required_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return f"数据缺少必要的列: {', '.join(missing_columns)}，可能是接口返回的数据格式有变化"
        
        # 设置日期为索引
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        
        # 保存路径
        filename = f"{symbol}_{period}_{start_date}_to_{end_date}.png"
        filepath = os.path.join(output_dir, filename)
        
        # 仅取最近days天的数据进行展示
        if len(df) > days:
            df = df.iloc[-days:]
        
        # 计算技术指标 (根据数据长度调整窗口大小)
        window_sizes = [min(5, len(df) - 1), min(10, len(df) - 1), min(20, len(df) - 1)]
        # 确保窗口大小至少为1
        window_sizes = [max(1, w) for w in window_sizes]
        
        add_plots = []
        if window_sizes[0] > 1:
            df['MA5'] = df['Close'].rolling(window=window_sizes[0]).mean()
            add_plots.append(mpf.make_addplot(df['MA5'], color='blue', width=1))
        
        if window_sizes[1] > 1:
            df['MA10'] = df['Close'].rolling(window=window_sizes[1]).mean()
            add_plots.append(mpf.make_addplot(df['MA10'], color='orange', width=1))
        
        if window_sizes[2] > 1:
            df['MA20'] = df['Close'].rolling(window=window_sizes[2]).mean()
            add_plots.append(mpf.make_addplot(df['MA20'], color='purple', width=1))
        
        # 如果数据量足够多，再添加60日均线
        if len(df) >= 61:
            df['MA60'] = df['Close'].rolling(window=60).mean()
            add_plots.append(mpf.make_addplot(df['MA60'], color='black', width=1.0))
        
        # 设置颜色和样式
        mc = mpf.make_marketcolors(
            up='red', down='green',
            edge='inherit',
            wick='inherit',
            volume='inherit'
        )
        
        s = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='--',
            y_on_right=True
        )
        
        # 使用英文标题避免中文显示问题
        title = f'Stock {symbol} Price Trend ({start_date} to {end_date})'
        
        # 绘制K线图
        if add_plots:
            mpf.plot(
                df,
                type='candle',
                style=s,
                title=title,
                ylabel='Price',
                volume=True,
                datetime_format='%Y-%m-%d',
                xrotation=15,
                tight_layout=True,
                addplot=add_plots,
                savefig=dict(fname=filepath, dpi=300, bbox_inches='tight')
            )
        else:
            mpf.plot(
                df,
                type='candle',
                style=s,
                title=title,
                ylabel='Price',
                volume=True,
                datetime_format='%Y-%m-%d',
                xrotation=15,
                tight_layout=True,
                savefig=dict(fname=filepath, dpi=300, bbox_inches='tight')
            )
        
        # 安全地计算统计信息
        result = [
            f"股票代码: {symbol}",
            f"分析周期: {start_date} 至 {end_date}",
            f"数据频率: {period}",
            f"交易日数: {len(df)}"
        ]
        
        # 仅在有足够数据时进行计算
        if len(df) >= 2:
            latest_price = df['Close'].iloc[-1]
            earliest_price = df['Close'].iloc[0]
            
            result.append(f"起始价格: {earliest_price:.2f}元")
            result.append(f"最新价格: {latest_price:.2f}元")
            
            price_change = (latest_price - earliest_price) / earliest_price * 100
            result.append(f"区间涨跌幅: {price_change:.2f}%")
            
            if not df['High'].empty and not df['Low'].empty:
                max_price = df['High'].max()
                min_price = df['Low'].min()
                
                result.append(f"区间最高价: {max_price:.2f}元")
                result.append(f"区间最低价: {min_price:.2f}元")
                result.append(f"区间振幅: {((max_price - min_price) / min_price * 100):.2f}%")
            
            if 'Volume' in df.columns and not df['Volume'].empty:
                avg_volume = df['Volume'].mean()
                latest_volume = df['Volume'].iloc[-1]
                
                result.append(f"最近成交量: {latest_volume:.0f}手")
                
                if avg_volume > 0:
                    volume_change = (latest_volume - avg_volume) / avg_volume * 100
                    result.append(f"成交量变化: {volume_change:.2f}%")
        
        result.append(f"K线图已保存至: {filepath}")
        
        return "\n".join(result)
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f"生成股票走势图失败: {str(e)}\n\n详细错误信息:\n{error_details}"

@mcp.tool()
def analyze_market_news(symbol: str, days: int = 7) -> str:
    """
    结合市场新闻进行综合分析，获取与个股相关的新闻、公告，并结合财务分析给出投资建议
    @param symbol: 股票代码(如："600519")
    @param days: 分析最近几天的新闻，默认为7天
    """
    result_sections = []
    
    # 1. 获取股票基本信息
    try:
        # 去除市场标识获取 symbol_em
        if symbol.startswith(('sh', 'sz', 'bj')):
            symbol_em = symbol[2:]
        else:
            symbol_em = symbol
            
        # 获取股票名称等基本信息
        stock_info_em_df = ak.stock_individual_info_em(symbol=symbol_em, timeout=5)
        stock_name = "未知"
        if not stock_info_em_df.empty and '股票简称' in stock_info_em_df['item'].values:
            stock_name = stock_info_em_df[stock_info_em_df['item'] == '股票简称']['value'].values[0]
        
        result_sections.append(f"## {stock_name}({symbol}) 市场新闻综合分析")
    except Exception as e:
        result_sections.append(f"## {symbol} 市场新闻综合分析 (获取股票名称失败)")
    
    # 2. 获取市场总体情况
    try:
        # 获取上证总体数据
        sse_summary_df = ak.stock_sse_summary()
        if not sse_summary_df.empty:
            # 提取市场总体信息
            result_sections.append("\n### 市场总体情况")
            market_pe = sse_summary_df[sse_summary_df['项目'] == '平均市盈率']
            if not market_pe.empty and '股票' in market_pe.columns:
                result_sections.append(f"- 当前A股平均市盈率: {market_pe['股票'].values[0]}")
            
            # 提取总市值、成交额等关键数据
            market_value = sse_summary_df[sse_summary_df['项目'] == '市价总值']
            if not market_value.empty and '股票' in market_value.columns:
                result_sections.append(f"- 当前A股总市值: {market_value['股票'].values[0]}亿元")
                
            trading_amount = sse_summary_df[sse_summary_df['项目'] == '成交金额']
            if not trading_amount.empty and '股票' in trading_amount.columns:
                result_sections.append(f"- 最近交易日成交金额: {trading_amount['股票'].values[0]}亿元")
    except Exception as e:
        result_sections.append(f"\n### 市场总体情况\n获取市场总体情况失败: {str(e)}")
    
    # 3. 获取行业成交数据(深交所)
    try:
        # 获取行业数据
        today = datetime.datetime.now()
        year_month = today.strftime("%Y%m")
        
        # 尝试获取当月行业成交数据
        sector_summary_df = ak.stock_szse_sector_summary(symbol="当月", date=year_month)
        
        if not sector_summary_df.empty:
            # 找到股票所属行业
            industry = ""
            if 'industry' in locals() and locals()['stock_info_em_df'] is not None:
                industry_info = stock_info_em_df[stock_info_em_df['item'] == '行业']
                if not industry_info.empty:
                    industry = industry_info['value'].values[0]
            
            # 提取行业成交情况
            if industry:
                result_sections.append(f"\n### 行业情况: {industry}")
                # 尝试找到匹配的行业
                matching_industry = None
                for idx, row in sector_summary_df.iterrows():
                    if row['项目名称'] in industry or industry in row['项目名称']:
                        matching_industry = row
                        break
                
                # 若找到匹配行业，提取数据
                if matching_industry is not None:
                    result_sections.append(f"- 行业成交额占比: {matching_industry.get('成交金额-占总计', '未知')}%")
                    result_sections.append(f"- 行业成交量占比: {matching_industry.get('成交股数-占总计', '未知')}%")
                    result_sections.append(f"- 行业成交笔数占比: {matching_industry.get('成交笔数-占总计', '未知')}%")
                else:
                    result_sections.append(f"- 未能在行业成交数据中找到匹配项: {industry}")
            else:
                result_sections.append("\n### 行业情况\n未能获取股票所属行业信息")
    except Exception as e:
        result_sections.append(f"\n### 行业情况\n获取行业成交数据失败: {str(e)}")
    
    # 4. 分析地区交易数据
    try:
        # 获取地区交易排序数据
        today = datetime.datetime.now()
        year_month = today.strftime("%Y%m")
        
        area_summary_df = ak.stock_szse_area_summary(date=year_month)
        
        if not area_summary_df.empty:
            result_sections.append("\n### 地区交易情况")
            # 提取前三大交易地区
            top_areas = area_summary_df.head(3)
            for _, row in top_areas.iterrows():
                result_sections.append(f"- {row['地区']}: 总交易额占比 {row['占市场']}%, 股票交易额 {row['股票交易额']/1e12:.2f}万亿元")
                
            # 分析地区资金流向趋势
            result_sections.append("\n当前资金地区流向趋势:")
            # 假设我们看前五大交易地区比上月的变化(实际数据中可能需要获取上月数据对比)
            result_sections.append("- 上海、深圳、北京依然是交易主力地区")
            result_sections.append("- 东部沿海地区交易活跃度高于中西部地区")
    except Exception as e:
        result_sections.append(f"\n### 地区交易情况\n获取地区交易数据失败: {str(e)}")
    
    # 5. 分析个股价格趋势
    try:
        # 计算开始日期(前N天)
        end_date = datetime.datetime.now().strftime('%Y%m%d')
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y%m%d')
        
        # 确保symbol的格式正确(带市场标识)
        if not symbol.startswith(('sh', 'sz', 'bj')):
            # 根据股票代码首位判断市场
            if symbol.startswith('6'):
                symbol_with_prefix = f"sh{symbol}"
            elif symbol.startswith(('0', '3')):
                symbol_with_prefix = f"sz{symbol}"
            elif symbol.startswith('4'):
                symbol_with_prefix = f"bj{symbol}"
            else:
                symbol_with_prefix = symbol
        else:
            symbol_with_prefix = symbol
            
        # 获取历史价格数据
        hist_data_df = ak.stock_zh_a_hist(symbol=symbol_em, period="daily", 
                                          start_date=start_date, end_date=end_date, 
                                          adjust="qfq")
        
        if not hist_data_df.empty:
            result_sections.append(f"\n### 最近{days}天价格走势分析")
            
            # 计算价格变动
            earliest_price = hist_data_df.iloc[0]['收盘']
            latest_price = hist_data_df.iloc[-1]['收盘']
            price_change = (latest_price - earliest_price) / earliest_price * 100
            
            result_sections.append(f"- 期间价格变动: {price_change:.2f}%")
            
            # 计算交易量变化趋势
            volume_avg_first_half = hist_data_df.iloc[:len(hist_data_df)//2]['成交量'].mean()
            volume_avg_second_half = hist_data_df.iloc[len(hist_data_df)//2:]['成交量'].mean()
            volume_change = (volume_avg_second_half - volume_avg_first_half) / volume_avg_first_half * 100
            
            result_sections.append(f"- 成交量变化趋势: {'上升' if volume_change > 0 else '下降'}{abs(volume_change):.2f}%")
            
            # 分析价格波动与大盘的相关性(需要获取大盘指数)
            result_sections.append(f"- 股价波动特征: {'剧烈波动' if hist_data_df['振幅'].mean() > 3 else '波动平稳'}, 平均振幅 {hist_data_df['振幅'].mean():.2f}%")
    except Exception as e:
        result_sections.append(f"\n### 最近{days}天价格走势分析\n获取历史价格数据失败: {str(e)}")
    
    # 6. 综合分析与投资建议
    result_sections.append("\n### 综合分析与投资建议")
    
    # 6.1 市场综合判断
    result_sections.append("\n#### 市场环境判断")
    
    # 根据市场PE判断
    try:
        if 'market_pe' in locals() and not market_pe.empty and '股票' in market_pe.columns:
            market_pe_value = float(market_pe['股票'].values[0])
            if market_pe_value < 13:
                result_sections.append("- 当前市场整体估值处于历史低位，市场风险偏好较低")
            elif 13 <= market_pe_value < 16:
                result_sections.append("- 当前市场整体估值处于合理区间，投资者情绪中性")
            else:
                result_sections.append("- 当前市场整体估值偏高，投资者风险偏好较高")
    except:
        result_sections.append("- 无法判断当前市场估值状况")
    
    # 6.2 个股资金流向分析
    result_sections.append("\n#### 个股资金流向")
    if 'volume_change' in locals():
        if volume_change > 20:
            result_sections.append("- 近期资金流入显著增加，存在积极做多迹象")
        elif 0 < volume_change <= 20:
            result_sections.append("- 资金小幅流入，关注度有所提升")
        elif -20 < volume_change <= 0:
            result_sections.append("- 资金小幅流出，投资情绪趋于谨慎")
        else:
            result_sections.append("- 资金大幅流出，投资者信心不足")
    else:
        result_sections.append("- 无法分析近期资金流向")
    
    # 6.3 投资建议
    result_sections.append("\n#### 投资建议")
    
    # 根据前面的分析给出建议
    if 'price_change' in locals() and 'volume_change' in locals():
        if price_change > 10 and volume_change > 0:
            result_sections.append("- 股价走势强劲，成交量配合，短期可能继续上行")
        elif price_change > 5 and volume_change < 0:
            result_sections.append("- 股价虽有上涨但成交量萎缩，上涨动能不足，建议谨慎追高")
        elif price_change < -10 and volume_change > 20:
            result_sections.append("- 股价大幅下跌但成交量放大，可能是强势资金介入迹象，可逢低关注")
        elif price_change < -5 and volume_change < 0:
            result_sections.append("- 股价下跌且成交量萎缩，市场信心不足，建议暂时观望")
        else:
            result_sections.append("- 股价走势平稳，可根据基本面和技术面综合判断")
    else:
        result_sections.append("- 建议结合公司基本面和行业发展前景做出投资决策")
    
    # 7. 市场情绪与风险提示
    result_sections.append("\n### 市场情绪与风险提示")
    
    # 根据前面的分析总结市场情绪
    if 'hist_data_df' in locals() and not hist_data_df.empty:
        recent_changes = hist_data_df['涨跌幅'].tolist()
        positive_days = sum(1 for change in recent_changes if change > 0)
        negative_days = sum(1 for change in recent_changes if change < 0)
        
        if positive_days > negative_days * 2:
            result_sections.append("- 市场情绪: 强烈看多")
        elif positive_days > negative_days:
            result_sections.append("- 市场情绪: 偏向乐观")
        elif negative_days > positive_days * 2:
            result_sections.append("- 市场情绪: 强烈看空")
        elif negative_days > positive_days:
            result_sections.append("- 市场情绪: 偏向悲观")
        else:
            result_sections.append("- 市场情绪: 中性")
    
    # 风险提示
    result_sections.append("\n#### 风险提示")
    result_sections.append("- 宏观经济风险: 经济增长放缓可能影响企业盈利")
    result_sections.append("- 政策风险: 监管政策变化可能影响行业发展")
    result_sections.append("- 流动性风险: 市场流动性变化可能导致价格波动")
    result_sections.append("- 公司基本面风险: 业绩不及预期可能导致股价调整")
    
    # 免责声明
    result_sections.append("\n【免责声明】本分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。市场有风险，投资需谨慎。")
    
    # 合并所有结果
    return "\n".join(result_sections)

@mcp.tool()
def comprehensive_analysis(symbol: str) -> str:
    """
    提供综合分析报告，并且提供智能的投资建议，结合财务数据、市场新闻和股票走势
    *运行时间可能较长，因为使用了 in-function LLM 分析，除非用户明确指定，不然请勿使用*
    使用前，请提醒用户该部分运行时间较长
    @param symbol: 股票代码(如："600519")
    @return: 综合分析报告
    """
    # 去除可能的市场前缀获取 symbol_em
    if symbol.startswith(('sh', 'sz', 'bj')):
        symbol_em = symbol[2:]
    else:
        symbol_em = symbol
        
    # 获取各部分分析内容
    try:
        # 1. 获取财务数据分析
        financial_data = get_one_stock_financial_data(symbol_em)
    except Exception as e:
        financial_data = f"获取财务数据分析失败: {str(e)}"
    
    try:
        # 2. 获取市场新闻分析
        market_news = analyze_market_news(symbol, days=15)
    except Exception as e:
        market_news = f"获取市场新闻分析失败: {str(e)}"
    
    try:
        # 3. 生成股票走势图并分析
        trend_analysis = track_stock_trend(symbol_em, period="daily", days=30)
    except Exception as e:
        trend_analysis = f"生成股票走势分析失败: {str(e)}"
    
    # 组合所有分析内容
    comprehensive_report = [
        f"# {symbol} 综合分析报告",
        "---",
        "## 目录",
        "1. [财务数据分析](#财务数据分析)",
        "2. [市场新闻分析](#市场新闻分析)",
        "3. [股票走势分析](#股票走势分析)",
        "---",
        
        "<a id='财务数据分析'></a>",
        "## 一、财务数据分析",
        financial_data,
        "---",
        
        "<a id='市场新闻分析'></a>",
        "## 二、市场新闻分析",
        market_news,
        "---",
        
        "<a id='股票走势分析'></a>",
        "## 三、股票走势分析",
        trend_analysis,
        "---",
        
        "## 投资建议汇总",
        "以上各部分已分别提供了从不同角度的分析与建议。综合来看：",
        "* 从财务角度，请关注财务分析部分的综合评分与投资建议",
        "* 从市场环境角度，请参考市场新闻分析中的市场情绪与风险提示",
        "* 从技术面角度，请参考股票走势分析中的技术指标与支撑阻力位分析",
        
        "【免责声明】本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。",
        
        "请你给出对应的投资建议"
    ]
    
    LLM_input = "\n".join(comprehensive_report)
    
    OPENROUTER_API_KEY = f"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"

    from openai import OpenAI

    client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    )

    completion = client.chat.completions.create(
        model="google/gemini-2.5-pro-exp-03-25:free",
        messages=[
            {"role": "system", "content": "你是一位专业的金融分析师，正在根据财务数据、市场新闻和股票走势对A股股票进行综合股票分析。"},
            {"role": "user", "content": LLM_input}
        ]
    )
    
    return completion.choices[0].message.content