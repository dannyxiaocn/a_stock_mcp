# server.py
from mcp.server.fastmcp import FastMCP
import akshare as ak
import pandas as pd
import mplfinance as mpf
import datetime
import time

import os
import matplotlib.pyplot as plt
import tempfile

# 通用重试机制封装
def retry_get_data(func, max_retries=3, retry_interval=1, **kwargs):
    """
    通用数据获取重试机制
    :param func: 数据获取函数（如 ak.xxx）
    :param max_retries: 最大重试次数
    :param retry_interval: 每次重试间隔秒数
    :param kwargs: 传递给 func 的参数
    :return: func 返回值或抛出最后一次异常
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func(**kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
    raise last_exception

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
        stock_info_em_df = retry_get_data(ak.stock_individual_info_em, symbol=symbol_em, timeout=5)
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
        stock_info_xq_df = retry_get_data(ak.stock_individual_basic_info_xq, symbol=symbol_xq, timeout=5)
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
        stock_bid_ask_df = retry_get_data(ak.stock_bid_ask_em, symbol=symbol_em)
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
        
        hist_data_df = retry_get_data(
            ak.stock_zh_a_hist,
            symbol=symbol_em, period="daily", 
            start_date=start_date, end_date=end_date, 
            adjust="qfq"
        )
        
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
    
    # 4.1 获取预测年报净利润（同花顺）
    try:
        profit_forecast_df = retry_get_data(
            ak.stock_profit_forecast_ths,
            symbol=symbol_em,
            indicator="预测年报净利润"
        )
        if not profit_forecast_df.empty:
            result_sections.append("\n== 未来年度净利润预测（同花顺） ==")
            result_sections.append(profit_forecast_df.to_string(index=False))
        else:
            result_sections.append("\n未来年度净利润预测（同花顺）：暂无数据")
    except Exception as e:
        result_sections.append(f"\n获取未来年度净利润预测失败: {str(e)}")

    # 4.2 获取业绩快报（如有）
    try:
        year = datetime.datetime.now().year
        yjkb_df = retry_get_data(ak.stock_yjkb_em, symbol=symbol_em)
        if not yjkb_df.empty:
            result_sections.append("\n== 业绩快报（东方财富） ==")
            result_sections.append(yjkb_df.to_string(index=False))
        else:
            result_sections.append("\n业绩快报：暂无数据")
    except Exception as e:
        result_sections.append(f"\n获取业绩快报失败: {str(e)}")

    # 4.3 获取业绩预告（如有）
    try:
        year = datetime.datetime.now().year
        yjyg_df = retry_get_data(ak.stock_yjyg_em, symbol=symbol_em)
        if not yjyg_df.empty:
            result_sections.append("\n== 业绩预告（东方财富） ==")
            result_sections.append(yjyg_df.to_string(index=False))
        else:
            result_sections.append("\n业绩预告：暂无数据")
    except Exception as e:
        result_sections.append(f"\n获取业绩预告失败: {str(e)}")

    # 4.4 获取机构评级（如有）
    try:
        inst_recommend_df = retry_get_data(ak.stock_em_analyst_detail, symbol=symbol_em)
        if not inst_recommend_df.empty:
            result_sections.append("\n== 机构评级汇总（东方财富） ==")
            # 统计评级分布情况
            if '评级' in inst_recommend_df.columns:
                rating_counts = inst_recommend_df['评级'].value_counts().to_dict()
                result_sections.append("评级分布：" + ", ".join([f"{k}: {v}" for k,v in rating_counts.items()]))
            result_sections.append(inst_recommend_df.head(10).to_string(index=False))
        else:
            result_sections.append("\n机构评级：暂无数据")
    except Exception as e:
        result_sections.append(f"\n获取机构评级失败: {str(e)}")
        # 尝试备用API
        try:
            inst_recommend_df = retry_get_data(ak.stock_em_analyst_rank_institute)
            if not inst_recommend_df.empty:
                # 过滤出与当前股票相关的评级
                target_df = inst_recommend_df[inst_recommend_df['代码'] == symbol_em]
                if not target_df.empty:
                    result_sections.append("\n== 机构评级（备用API） ==")
                    result_sections.append(target_df.head(5).to_string(index=False))
            else:
                result_sections.append("\n备用机构评级：暂无数据")
        except Exception as sub_e:
            result_sections.append(f"\n备用机构评级API也失败: {str(sub_e)}")
    
    # 5. 财务分析
    result_sections.append("\n== 财务分析 ==")
    
    # 5.0 未来盈利预测分析
    if 'profit_forecast_df' in locals() and profit_forecast_df is not None and not profit_forecast_df.empty:
        try:
            result_sections.append("\n【未来盈利预测分析】")
            # 取最近两年预测
            for i, row in profit_forecast_df.iterrows():
                year = row['年度']
                avg = row['均值']
                minv = row['最小值']
                maxv = row['最大值']
                orgs = row['预测机构数']
                industry_avg = row['行业平均数']
                result_sections.append(f"{year}年预测净利润区间: {minv:.2f}~{maxv:.2f}，均值: {avg:.2f}，行业均值: {industry_avg:.2f}，机构数: {orgs}")
        except Exception as e:
            result_sections.append(f"未来盈利预测分析失败: {str(e)}")
    else:
        result_sections.append("\n【未来盈利预测分析】暂无数据")

    # 5.01 业绩快报/预告分析
    if 'yjkb_df' in locals() and yjkb_df is not None and not yjkb_df.empty:
        try:
            result_sections.append("\n【业绩快报分析】")
            # 取最新一期快报
            latest_yjkb = yjkb_df.iloc[0]
            if '归属于母公司股东的净利润-同比增长率' in latest_yjkb:
                yoy = latest_yjkb['归属于母公司股东的净利润-同比增长率']
                result_sections.append(f"最新业绩快报净利润同比增长率: {yoy}")
        except Exception as e:
            result_sections.append(f"业绩快报分析失败: {str(e)}")
    if 'yjyg_df' in locals() and yjyg_df is not None and not yjyg_df.empty:
        try:
            result_sections.append("\n【业绩预告分析】")
            latest_yjyg = yjyg_df.iloc[0]
            if '业绩预告内容' in latest_yjyg:
                result_sections.append(f"最新业绩预告: {latest_yjyg['业绩预告内容']}")
        except Exception as e:
            result_sections.append(f"业绩预告分析失败: {str(e)}")

    # 5.02 机构评级分析
    if 'inst_recommend_df' in locals() and inst_recommend_df is not None and not inst_recommend_df.empty:
        try:
            result_sections.append("\n【机构评级分析】")
            rating_counts = inst_recommend_df['评级'].value_counts().to_dict()
            result_sections.append("评级分布: " + ", ".join([f"{k}: {v}" for k,v in rating_counts.items()]))
            # 统计买入/增持/中性/卖出比例
            buy = rating_counts.get('买入', 0)
            add = rating_counts.get('增持', 0)
            neutral = rating_counts.get('中性', 0)
            sell = rating_counts.get('卖出', 0)
            total = sum(rating_counts.values())
            if total > 0:
                result_sections.append(f"买入+增持占比: {(buy+add)/total*100:.1f}%，中性占比: {neutral/total*100:.1f}%，卖出占比: {sell/total*100:.1f}%")
        except Exception as e:
            result_sections.append(f"机构评级分析失败: {str(e)}")
    
    # =======【增强：行业与市场对比分析】=======
    # 获取当前年份和月份，用于行业/板块数据
    now = datetime.datetime.now()
    current_year_month = now.strftime('%Y%m')
    current_date = now.strftime('%Y%m%d')

    # 1. 行业平均估值对比
    industry_name = stock_info_dict.get('行业', None)
    if industry_name:
        found_sector_data = False
        for i in range(0, 6):  # 最多回溯6个月
            try:
                dt = now - pd.DateOffset(months=i)
                ym = dt.strftime('%Y%m')
                sector_df = retry_get_data(ak.stock_szse_sector_summary, symbol="当年", date=ym)
                sector_row = sector_df[sector_df['项目名称'] == industry_name]
                if not sector_row.empty:
                    # ...（原有分析逻辑）
                    found_sector_data = True
                    break
            except Exception as e:
                continue
        if not found_sector_data:
            result_sections.append("行业数据获取失败（近半年无可用数据）")

    # 2. 市场整体估值与换手率对比（上交所）
    try:
        sse_summary_df = retry_get_data(ak.stock_sse_summary)
        if not sse_summary_df.empty:
            market_pe = sse_summary_df[sse_summary_df['项目'] == '平均市盈率']
            if not market_pe.empty and '股票' in market_pe.columns:
                market_avg_pe = market_pe['股票'].values[0]
                result_sections.append(f"A股整体平均市盈率: {market_avg_pe}")
                
                # 与个股市盈率比较
                if '市盈率' in stock_info_dict:
                    try:
                        stock_pe = float(stock_info_dict['市盈率'])
                        market_pe_value = float(market_avg_pe)
                        pe_diff = stock_pe - market_pe_value
                        pe_diff_pct = pe_diff / market_pe_value * 100
                        
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
    
    # 3. 行业活跃度分位（换手率、量比对比）
    if industry_name and bid_ask_dict:
        try:
            # 获取行业平均换手率（可扩展为更细致的分位数分析）
            # 这里只能用市场整体数据，若后续行业细分数据可得可进一步增强
            if '换手率' in bid_ask_dict:
                turnover_stock = float(bid_ask_dict['换手率'])
                # 用市场换手率做近似对比
                if 'turnover_market_val' in locals():
                    if turnover_stock > turnover_market_val:
                        result_sections.append("换手率高于市场平均，活跃度较高")
                    else:
                        result_sections.append("换手率低于市场平均，活跃度一般")
            if '量比' in bid_ask_dict:
                volume_ratio = float(bid_ask_dict['量比'])
                if volume_ratio > 2:
                    result_sections.append("量比显著高于市场，资金活跃")
                elif volume_ratio > 1:
                    result_sections.append("量比高于市场，成交较活跃")
                else:
                    result_sections.append("量比较低，成交一般")
        except Exception as e:
            result_sections.append(f"行业活跃度分位分析失败: {str(e)}")

    # 4. 阶段高低点分位分析
    if hist_data_df is not None and not hist_data_df.empty:
        try:
            close_prices = hist_data_df['收盘']
            latest_close = close_prices.iloc[-1]
            max_close = close_prices.max()
            min_close = close_prices.min()
            quantile = (latest_close - min_close) / (max_close - min_close) if max_close > min_close else 0
            result_sections.append(f"\n== 阶段高低点分位分析 ==\n")
            result_sections.append(f"近90日最高收盘: {max_close:.2f}元，最低收盘: {min_close:.2f}元")
            result_sections.append(f"当前收盘价分位: {quantile*100:.1f}%，处于近90日区间{'高位' if quantile>0.7 else '低位' if quantile<0.3 else '中位'}")
        except Exception as e:
            result_sections.append(f"阶段高低点分位分析失败: {str(e)}")

    # 5. 财务健康性指标与行业对比（如能获取到）
    # 可扩展：如雪球/东财接口有ROE、资产负债率等，可在此处补充行业均值对比
    # 暂留接口位
    # =====================================
    
    # 6. 深入财务指标分析（整合自calculate_key_financial_indicators）
    result_sections.append("\n=========== 深入财务指标分析 ===========")
    
    # 6.1 获取年度历史数据（如果之前的历史数据不足1年）
    try:
        # 重新获取一年的历史数据，用于计算年化指标
        if hist_data_df is None or len(hist_data_df) < 250:
            end_date = datetime.datetime.now().strftime('%Y%m%d')
            start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y%m%d')
            
            annual_hist_data_df = retry_get_data(
                ak.stock_zh_a_hist,
                symbol=symbol_em, period="daily", 
                start_date=start_date, end_date=end_date, 
                adjust="qfq"
            )
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
        stock_sse_summary_df = retry_get_data(ak.stock_sse_summary)
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
                        pe_diff = stock_pe - market_pe_value
                        pe_diff_pct = pe_diff / market_pe_value * 100
                        
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
        stock_data = retry_get_data(
            ak.stock_zh_a_hist,
            symbol=symbol, period=period, 
            start_date=start_date, 
            end_date=end_date, 
            adjust="qfq"
        )
        
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
def analyze_market_news(symbol: str, days: int = 30) -> str:
    """
    结合市场新闻进行综合分析，获取与个股相关的新闻、公告，并结合财务分析给出投资建议
    @param symbol: 股票代码(如："600519")
    @param days: 分析最近几天的新闻，默认为30天
    """
    result_sections = []
    try:
        # 获取个股新闻
        df_news = retry_get_data(ak.stock_news_em, symbol=symbol)
        df_news['发布时间'] = pd.to_datetime(df_news['发布时间'], errors='coerce')
        start_dt = datetime.datetime.now() - datetime.timedelta(days=days)
        recent = df_news[df_news['发布时间'] >= start_dt]
        count_news = len(recent)
        result_sections.append("市场活跃度")
        result_sections.append(f"- 最近{days}天共抓取相关新闻 {count_news} 条")
        if '新闻链接' in recent.columns:
            recent = recent.drop(columns=['新闻链接'])
        result_sections.append("\n== 个股新闻原始数据 ==")
        result_sections.append(str(recent))
        # 市场情绪指标
        pos = recent['新闻标题'].str.contains('涨|上涨|反弹', regex=True).sum()
        neg = recent['新闻标题'].str.contains('跌|下跌|回调', regex=True).sum()
        sentiment = (pos - neg) / count_news * 100 if count_news else 0
        result_sections.append("市场情绪指标")
        result_sections.append(f"- 正面新闻 {pos} 条，负面新闻 {neg} 条，情绪倾向 {sentiment:.2f}%")
        # 市场总体资金流向
        end_dt = datetime.datetime.now()
        start_str = (end_dt - datetime.timedelta(days=days)).strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")
        hgt_df = retry_get_data(ak.stock_hsgt_hist_em, symbol="北向资金")
        net_total = hgt_df["当日资金流入"].sum() if not hgt_df.empty else 0
        result_sections.append("市场总体资金流向")
        result_sections.append(f"- 近{days}天北向资金累计净流入 {net_total:.2f} 亿元")
        result_sections.append("\n== 北向资金原始数据 ==")
        result_sections.append(str(hgt_df))
        # 北向资金
        avg_daily = net_total / days if days else 0
        result_sections.append("北向资金")
        result_sections.append(f"- 平均每日净流入 {avg_daily:.2f} 亿元")
        # 行业板块
        br_df = retry_get_data(ak.stock_hsgt_board_rank_em, symbol="北向资金增持行业板块排行", indicator="今日")
        top3 = br_df.head(3)["名称"].tolist() if not br_df.empty else []
        result_sections.append("行业板块")
        result_sections.append(f"- 北向资金今日增持最多的行业板块: {', '.join(top3)}")
        result_sections.append("\n== 行业板块原始数据 ==")
        result_sections.append(str(br_df))
        # 个股资金流（东方财富）
        market = 'sh' if symbol.startswith('6') else 'sz'
        try:
            ind_fund_df = retry_get_data(ak.stock_individual_fund_flow, stock=symbol, market=market)
            result_sections.append("\n== 个股资金流(东方财富) ==")
            result_sections.append(str(ind_fund_df))
        except Exception as e:
            result_sections.append(f"\n获取个股资金流失败: {str(e)}")
        # 全球财经快讯-东财财富
        try:
            global_em_df = retry_get_data(ak.stock_info_global_em)
            if 'code' in global_em_df.columns:
                global_em_df = global_em_df.drop(columns=['code'])
            result_sections.append("\n== 全球财经快讯-东财财富 ==")
            result_sections.append(str(global_em_df))
        except Exception as e:
            result_sections.append(f"\n获取全球财经快讯-东财财富失败: {str(e)}")
        # 全球财经快讯-新浪财经
        try:
            global_sina_df = retry_get_data(ak.stock_info_global_sina)
            result_sections.append("\n== 全球财经快讯-新浪财经 ==")
            result_sections.append(str(global_sina_df))
        except Exception as e:
            result_sections.append(f"\n获取全球财经快讯-新浪财经失败: {str(e)}")
        # 全球财经快讯-富途牛牛
        try:
            global_futu_df = retry_get_data(ak.stock_info_global_futu)
            if '链接' in global_futu_df.columns:
                global_futu_df = global_futu_df.drop(columns=['链接'])
            result_sections.append("\n== 全球财经快讯-富途牛牛 ==")
            result_sections.append(str(global_futu_df))
        except Exception as e:
            result_sections.append(f"\n获取全球财经快讯-富途牛牛失败: {str(e)}")
        # 全球财经直播-同花顺财经
        try:
            global_ths_df = retry_get_data(ak.stock_info_global_ths)
            if '链接' in global_ths_df.columns:
                global_ths_df = global_ths_df.drop(columns=['链接'])
            result_sections.append("\n== 全球财经直播-同花顺财经 ==")
            result_sections.append(str(global_ths_df))
        except Exception as e:
            result_sections.append(f"\n获取全球财经直播-同花顺财经失败: {str(e)}")
        # 电报-财联社
        try:
            global_cls_df = retry_get_data(ak.stock_info_global_cls, symbol="全部")
            result_sections.append("\n== 电报-财联社 ==")
            result_sections.append(str(global_cls_df))
        except Exception as e:
            result_sections.append(f"\n获取电报-财联社失败: {str(e)}")
        # 投资建议
        result_sections.append("投资建议")
        if count_news and sentiment > 0 and net_total > 0:
            advice = "当前市场情绪偏多，资金流入较好，建议继续关注买入机会。"
        elif count_news and sentiment < 0 and net_total < 0:
            advice = "当前市场情绪偏空，资金流出较多，建议谨慎观望。"
        else:
            advice = "市场情绪和资金流向波动剧烈，建议保持观望，等待更明朗的信号。"
        result_sections.append(f"- {advice}")
        return "\n".join(result_sections)
    except Exception as e:
        return f"获取市场新闻分析失败: {str(e)}"

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
    
    OPENROUTER_API_KEY = "API-KEY"

    from openai import OpenAI

    client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    )

    completion = client.chat.completions.create(
        model="google/gemini-2.5-pro-preview-03-25",
        messages=[
            {"role": "system", "content": "你是一位专业的金融分析师，正在根据财务数据、市场新闻和股票走势对A股股票进行综合股票分析。"},
            {"role": "user", "content": LLM_input}
        ]
    )
    
    return completion.choices[0].message.content