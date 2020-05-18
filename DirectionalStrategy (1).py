#!/usr/bin/env python
# coding: utf-8

# In[1]:


import datetime as dt
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.core.debugger import set_trace


# In[2]:


def to_datetime(label):
    return dt.datetime.strptime(label,"%Y-%m-%d %H:%M:%S")
BNFSpotData: pd.DataFrame = pd.read_csv("banknifty5min.csv")
BNFSpotData.datetime = BNFSpotData.datetime.apply(to_datetime)
BNFSpotData["Date"] = BNFSpotData.datetime.apply(lambda x: x.date())
print(BNFSpotData.Date)
BNFSpotData["Time"] = BNFSpotData.datetime.apply(lambda x: x.time())
BNFSpotData.set_index(["Date","Time"], inplace=True)
BNFSpotData.sort_index(inplace=True)
BNFSpotData = BNFSpotData.drop(["datetime","volume"],axis=1)


# In[137]:


class Order:
    '''
        REPRESENTS an Order object of some type - LONG/SHORT/SQUARE
    '''
    def __init__(self,time,price,action,qty=1):
        self.timestamp = time
        self.price = price
        self.qty = qty
        self.action = action
        self.str_action=None
        if action==1:
            self.str_action = "LONG"
        elif action==-1:
            self.str_action = "SHORT"
        else:
            self.str_action = "SQUARE"
    def __str__(self):
        return "Time : {}\nPrice : {}\nQuantity : {}\nAction : {}".format(self.timestamp,self.price,self.qty,self.str_action)


# In[138]:


class DirectionalStrategy:
    def __init__(self, data,strategy='1',trail=False):
        '''
            Variables : 
                1. self._log -> maintains log of buy/sell/square orders with the latest corrosponding spl/shp lpl/lph used to check the condition to give the order
                2. self._data -> the dataframe
                3. self._curr_date -> date of current row
                4. self._gap_up and self._gap_down -> shows which(or none) among trade rules are satisfied
                5. self._buy_level -> with which we compare the price when we give an order
                6. self._trailing_sl -> If trail option is true
                7. self._latest -> latest among last LPL/LPH
                8. self._LPL, self._LPH, self._sph, self._spl = arrays of all LPL,LPH,SPH,SPL
                9. self._data (I,II,0) are rows (current-1,current-2,current)
               10. self._orders -> list of all orders
               11. self.position -> current position 1: LONG/SHORT,  0: SQUARE/NONE
               12. self._pnl -> cumulative profit
               13. self._cumPnl -> array of cumulative profit for all trades till now
               14. self._PnL -> array of P&L of individual trades
               15. self._trades -> number of trades done 
               16. self._stoploss, self._trailstoploss, self._target -> strategy setting parameters
            
            Functions :
                1. run - The Driver Function of the strategy class
                2. check_gap 
                     Date Change Phemonemom:-
        We check if there was a date change between today and yesterday. If there is then we check for gap up and gap down possibilities
        along with ability to implement trading rule 2 or 3 given by variables self._gap_up and self._gap_down.
        If there is such implementation of rule 2/3  available, then do that and create a new order.

        If Date changes then on the first entry of new date we check if last entry's date is diff from today's date
        If different, get the last order and check if it was a squaring order. If it wasn't then create a new squaring order 
                3. get_sph_or_spl - if both are not there then check for both of them. Whichever found then alters a switch to other side
                        so next time we check only for the alternative one. Also for a given row, the function returns
                        if it found a new spl, sph or none.
                            a. find_spl - checks for spl conditions and returns true if spl is found at current-2 row
                            b. find_sph - similar
                4. _check_sell - checks SL Breach or TARGET acquisition and squares off
                    a. squareOff - creates a SQUARE order 
                5. _check_buy - 
                    Initiating LONG Order - Check if there is some buy level already created. If yes then if price of data0 greater than
                                the buy level then go LONG
                                If no buy_level till then, check for the next SPH>LPH and set SPH as buy_level
                                In case buy level already exists and there is a new SPH5>LPH then first make a 
                                    LONG order then set the new buy level as SPH5 and go to next row
                    Initiating SHORT Order - similar
                        a. buy_or_short - create a LONG/SHORT order as commanded
                    Also Checks for LPL/LPH formation post initiating buy/sell orders
                        a. find_lpl - checks for downward trends in SPL and SPH and if all conditions satisfy then create a LPL
                                      checks if past 3 SPL and past 3 SPH are in downtrend -- use 2 SPH if only 2 are found till then
                        b. find_lph - similar
                                 STATIC-METHODS - check_uptrend and check_downtrend - to check for trends in any 3 numbers a,b,c
                        
                6. plot -> plots some data for the strategy based on the argument supplied
                7. summary - tries to give an backtest report format summary
        '''
        self._log = []
        self._data = data
        self._curr_date  = data.iloc[0].name[0]
        self._gap_up = 0
        self._gap_down = 0
        self._buy_level = 0
        self._trailing_sl = trail
        self._latest = None
        
#         self._LPL= []
#         self._LPH= []
        self._sph = []
        self._spl = []
#         self._curr_spl = -1
#         self._curr_sph = -1
        self._switch = 0
        
        self._lph = None
        self._lpl = None
        
        self._dataI = None
        self._dataII = None
        self._data0 = None
        
        self.orders = []
        self.position = 0
        
        self._stoploss = 0.003
        self._trailstoploss = 0.01
        self._target = 0.005
        self._pnl = 0
        self._trades = 0
        self._PnL = []
        self._cumPnL = []
        
    def __doc__(self):
        return '''
        @Author : Dhairya Jain
        Strategy Name - Directional Strategy
        Instrument Type - Equity
        Time Frame - {} to {}
        Strating Equity - BankNifty
        Entry Logic - Go long if uptrend and short if downtrend
        Exit Logic - Stoploss Breach or Target Acquired or EOD
        Target - {}%
        Stoploss - {}%
        Fixed Risk - ????
        Position Sizing - 1
        Instrument Type - Equity
        Leverage - None
    '''.format(self._data.index.levels[0][0],self._data.index.levels[0][-1],self._target*100,self._stoploss*100)
    def check_gap(self):
        if(self._curr_date!=self._dataI.name[0]):
            try:
                self._gap_down = self._dataI.low > self._data0.open and self._lpl[1] > self._data0.open
                self._gap_up = self._dataI.high < self._data0.open and self._lph[1] < self._data0.open
            except:
                pass
            if len(self.orders)>0 and self.orders[-1].str_action != "SQUARE":
                o = self.orders[-1]
                pl = (self._dataI.close - o.price)*o.action
                self.orders.append(self.squareOff(pl,(self._dataI.name,self._dataI.close)))
            print("\n\n\nDATE CHANGE : {}\n\n\n".format(self._curr_date))
            if self._gap_down:
                print("GAP DOWN\n\n\n")
            elif self._gap_up:
                print("GAP UP\n\n\n")
    def get_sph_or_sph(self,i):
        new_spl_sph = 0
        if self._switch ==0:
            spl = self._find_spl()
            if not spl:
                sph = self._find_sph()
                if sph:
                    new_spl_sph = 1
                    print("FIRST FOUND : SPH :At Time {}\t with Points - {}".format(self._sph[-1][0][1],self._sph[-1][1])," -- > entry = ",i-2," && i = ",i) 
            else:
                new_spl_sph = -1
                print("FIRST FOUND : SPL :At Time {}\t with Points - {}".format(self._spl[-1][0][1],self._spl[-1][1])," -- > entry = ",i-2," && i = ",i)
        elif self._switch==1:
            sph = self._find_sph()
            if sph:
                new_spl_sph = 1
                print("NOW FOUND : SPH :At Time {}\t with Points - {}".format(self._sph[-1][0][1],self._sph[-1][1])," -- > entry = ",i-2," && i = ",i)
        else:
            spl = self._find_spl()
            if spl:
                new_spl_sph = -1
                print("NOW FOUND : SPL :At Time {}\t with Points - {}".format(self._spl[-1][0][1],self._spl[-1][1])," -- > entry = ",i-2," && i = ",i)
#         if(new_spl_sph==-1 and len(self._spl)>=4):
#             self._buy_level = self._spl[-1]
#         elif(new_spl_sph==1 and len(self._sph)>=4):
#             self._buy_level = self._sph[-1]
        return new_spl_sph
    def _check_buy(self,i,new_spl_sph):
        if self.position !=1:      
            # If already (2,3) SPL&SPH found then find LPL and LPH
            if self._buy_level:
                if self._latest == self._lpl:
                    print(self._data0.close, self._buy_level)
                    if self._data0.close <= self._buy_level:
                        self.orders.append(self.buy_or_short((self._data0.name,self._data0.close),action=-1))
                elif self._latest == self._lph:
                    if self._data0.close >= self._buy_level:
                        self.orders.append(self.buy_or_short((self._data0.name,self._data0.close),action=1))
                    
                
                    
            if len(self._sph)>=3 or len(self._spl)>=3:
                # If already found 1 LPL OR LPH then 
                if self._latest:
                    if new_spl_sph==-1 and self._latest == self._lpl and self._spl[-1][1]<self._lpl[1]:
                        self._buy_level = self._spl[-1][1]
                    elif new_spl_sph==1 and self._latest == self._lph and self._sph[-1][1]>self._lph[1]:
                        self._buy_level = self._sph[-1][1]
                self._find_lph(i)
                self._find_lpl(i)
        return i+1
    def _check_sell(self):
        if self.position==1:
            for o in self.orders[-1:]:
                pl = (self._data0.close - o.price)*o.action
                if self._data0.close*o.action <= ((1-self._stoploss*o.action)*o.price) *o.action:
                    self.orders.append(self.squareOff(pl))
                elif self._data0.close*o.action >= ((1+self._target*o.action)*o.price)*o.action:
                    self.orders.append(self.squareOff(pl))
        elif self.position==0:
            pass
    def buy_or_short(self, data, action):
        self.position = 1
        o = Order(data[0],data[1],action)
        if action == 1:
            print("BUYING")
        elif action == -1:
            print("SELLING")
        self._log.append([o.timestamp,o.str_action,o.price,self._latest,self._spl[-1],self._sph[-1]])
        self._cumPnL.append(self._pnl)
        return o
    def squareOff(self,pl,data=None):
        self._PnL.append(pl)
        self._pnl += pl
        self._cumPnL.append(self._pnl)
        self._trades +=1
                    
        data = data or (self._data0.name,self._data0.close)
        self.position = 0
        o = Order(data[0],data[1],action=0)
        print("SQUARING at Price : {}\nTime : {}".format(data[1],data[0]))
        self._log.append([o.timestamp,o.str_action,o.price,self._latest,self._spl[-1],self._sph[-1]])
        return o
    
    @staticmethod
    def check_uptrend(a,b,c):
        if c>b and b>a:
            return True
        else:
            return False
    
    @staticmethod
    def check_downtrend(a,b,c):
        if c<b and b<a:
            return True
        else:
            return False
    def _find_lph(self,i):
        try:
            a,b,c = self._sph[-3:]
            a,b,c = a[1],b[1],c[1]
        except:
            b,c = self._sph[-2:]
            b,c = b[1],c[1]
            a = b-1
            if len(self._sph)<3:
                print("Here")
                return
        try:
            p,q,r = self._spl[-3:]
            p,q,r = p[1],q[1],r[1]
        except ValueError:
            q,r = self._spl[-2:]
            q,r = q[1],r[1]
            p = q - 1
        if self.check_uptrend(a,b,c) and self.check_uptrend(p,q,r):
            if True or self._data0.close<=self._spl[-1][1]:
                if self._sph[-1] != self._lph:
                    self._lph = self._sph[-1]
                    self._latest = self._lph
#                     self._LPH.append(self._lph)
                    print("LPH Found : {} --> {}\n".format(self._lph,i))
    def _find_lpl(self,i):
        try:
            a,b,c = self._spl[-3:]
            a,b,c = a[1],b[1],c[1]
        except:
            b,c = self._spl[-2:]
            b,c = b[1],c[1]
            a = b + 1
            if len(self._spl)<3:
                return
        
        try:
            p,q,r = self._sph[-3:]
            p,q,r = p[1],q[1],r[1]
        except ValueError:
            q,r = self._sph[-2:]
            q,r = q[1],r[1]
            p = q + 1        
        if self.check_downtrend(a,b,c) and self.check_downtrend(p,q,r):
            if True or self._data0.close>=self._sph[-1][1]:
                if self._spl[-1] != self._lpl:
                    self._lpl = self._spl[-1]
                    self._latest = self._lpl
#                     self._LPL.append(self._lpl)
                    print("LPL Found : {} --> {}\n".format(self._lpl,i))
    def _find_spl(self):
        if self._dataI.high > self._dataII.high and self._dataI.close > self._dataII.close:
            if self._data0.high > self._dataI.high and self._data0.close > self._dataI.close:
                self._spl.append((self._dataII.name, self._dataII.low))
#                 if len(self._spl)>=3:
#                     self._curr_spl +=1
                self._switch = 1
                return True
    def _find_sph(self):
        if self._dataI.low < self._dataII.low and self._dataI.close < self._dataII.close:
            if self._data0.low < self._dataI.low and self._data0.close < self._dataI.close:
                self._sph.append((self._dataII.name,self._dataII.high))
#                 if len(self._sph)>=3:
#                     self._curr_sph +=1
                self._switch = -1
                return True
    def plot(self,mode  = 'pnl'):
        if mode=='pivots':
            t = pd.DataFrame(self._sph, columns=['DT','Val'])
            ax1 = t.plot(x="DT",y="Val", style='.', c="DarkBlue", label = "SPH")
            
            x = pd.DataFrame(self._spl, columns=["DT",'Val'])
            x.plot(x="DT",y="Val", style='.',c="Red", ax= ax1, label="SPL")
#             lpl = pd.DataFrame(self._LPL, columns=["DT",'Val'])
#             lpl.plot(x="DT",y="Val", style='.',c="Black", ax= ax1, label="LPL")
#             lph = pd.DataFrame(self._LPH, columns=["DT",'Val'])
#             lph.plot(x="DT",y="Val", style='.',c="Yellow", ax= ax1, label="LPH")
        else:
            x = pd.Series(self._PnL)
            print(x)
            x.plot()
#         trunc = lambda x: x.strip("()").split(" ")[0]
#         tl = [ trunc(t.get_text()) for t in ax.get_xticklabels()]
#         ax.set_xticklabels(tl)
    def run(self):
        i = 2
        print("Begining with data entry : %d\n\n\n\n"%i)
        while(i<len(self._data)):
            # Code to Find Alternating SPL and SPH
            self._data0 = self._data.iloc[i]
            self._curr_date = self._data.iloc[i].name[0]
            self._dataI = self._data.iloc[i-1]
            self._dataII = self._data.iloc[i-2]
            
            #Check for day change and gap conditions
            self.check_gap() #Does nothing if date change doesn't occur
            
            #Find the next SPL SPH
            new_spl_sph  = self.get_sph_or_sph(i)
            # Sell if Already Bought
            self._check_sell()
            i = self._check_buy(i,new_spl_sph) 
        if len(self.orders)>0 and self.orders[-1].str_action != "SQUARE":
            o = self.orders[-1]
            pl = (self._dataI.close - o.price)*o.action
            self.orders.append(self.squareOff(pl,(self._data0.name,self._data0.close)))
        self._log = pd.DataFrame(self._log,columns=['Timestamp','Order Type','Price','Latest LPH or LPL','Last SPL','Last SPH'])
        self._log['P&L'] = pd.Series(self._cumPnL)
        print("\n\n\n\nNET PROFIT AND LOSS : %f"%self._pnl)
        print(self.summary())
    def summary(self):
        self._PnL = np.array(self._PnL)
        profit_trades = 0
        loss_trades = 0
        max_profit = self._PnL[0]
        max_loss = self._PnL[0]
        
        ml,mw=0, 0
        max_consecutive_wins = 0
        max_consecutive_loss = 0
        gross_profit = 0
        gross_loss = 0
        for i in range(len(self._PnL)):
            if self._PnL[i]>0:
                gross_profit += self._PnL[i]
                profit_trades+=1
                max_profit = max(max_profit,self._PnL[i])
                try:
                    if self._PnL[i-1]>0:
                        mw+=1
                        max_consecutive_wins=max(max_consecutive_wins,mw)
                    else:
                        mw=1
                except:        
                    pass
            elif self._PnL[i]<0:
                gross_loss += self._PnL[i]
                loss_trades+=1
                max_loss = min(max_loss,self._PnL[i])
                try:
                    if self._PnL[i-1]<0:
                        ml+=1
                        max_consecutive_loss=max(max_consecutive_loss,ml)
                    else:
                        ml=1
                except:
                    pass
        avg_profit = gross_profit/profit_trades
        avg_loss = gross_loss/loss_trades
        return '''
        
        NET PROFIT           : {}
        TOTAL TRADES         : {}
        MAX PROFIT           : {}
        MAX LOSS             : {}
        PROFITABLE TRADES    : {}
        LOSS TRADES          : {}
        AVG PROFIT           : {}
        AVG LOSS             : {}
        MAX CONSECUTIVE WINS : {}
        MAX CONSECUTIVE LOSS : {}
        
        '''.format(self._pnl,
                   len(self._PnL),
                   max_profit,
                   max_loss,
                   profit_trades,
                   loss_trades,
                   avg_profit,
                   avg_loss,
                   max_consecutive_wins,
                   max_consecutive_loss)


# In[139]:


strategy = DirectionalStrategy(BNFSpotData.iloc[(BNFSpotData.index.get_level_values('Date') >= dt.datetime(2019,11,1) ) & (BNFSpotData.index.get_level_values('Date') < dt.datetime(2020,1,1))])


# In[140]:


strategy.run()


# In[141]:


get_ipython().run_line_magic('matplotlib', 'notebook')
plt.plot(range(1,len(strategy._PnL)+1),strategy._PnL,label='nth trade')
a = []
for i in range(1,len(strategy._cumPnL),2):
    a.append(strategy._cumPnL[i])
plt.plot(range(1,len(a)+1),a,'r',label='Cumulative PnL')
plt.legend()
plt.xlabel("Number of Trades")
plt.ylabel("Profit - Loss")


# In[142]:


strategy.plot('pivots')


# In[129]:


strategy._log


# In[ ]:





# In[116]:


(strategy._log).to_csv("tradelog.csv")


# In[63]:


strategy._lpl[0]


# In[64]:


strategy._lph[0]


# In[65]:


pd.DataFrame(strategy._LPL, columns=["DT",'Val'])


# In[66]:


strategy._PnL


# In[16]:


strategy._curr_spl, strategy._curr_sph


# In[17]:


strategy._sph


# In[18]:


strategy._spl


# In[19]:


get_ipython().run_line_magic('matplotlib', 'notebook')
a = pd.DataFrame(strategy._sph)
a.set_index(a[0])
# plt.scatter(x = (a[0].apply(lambda x: str(x))), y = a[1])
b = pd.DataFrame(strategy._spl)
b.set_index(b[0])
# plt.scatter(x = (b[0].apply(lambda x: str(x))), y = b[1])
plt.plot(a[1])
plt.plot(b[1])


# In[39]:


get_ipython().run_line_magic('matplotlib', 'notebook')


a = BNFSpotData.iloc[BNFSpotData.index.get_level_values('Date') == dt.datetime(2019,2,8)]


# In[40]:


BNFSpotData.iloc[BNFSpotData.index.get_level_values('Date') == dt.datetime(2019,2,8)].plot()


# In[27]:


df = pd.DataFrame({'a':[2,3,5], 'b':[1,2,3], 'c':[12,13,14]})
df.set_index(['a','b'], inplace=True)
display(df)
s = df.iloc[1]


# In[96]:


BNFSpotData.iloc[BNFSpotData.index.get_level_values('Date') == dt.datetime(2019,2,11)]


# In[29]:


s.name[1]


# In[25]:


BNFSpotData.iloc[BNFSpotData.index.get_level_values('Date') == dt.datetime(2019,2,8)].iloc[30].name[1]


# In[ ]:


print('''
Date : {}
    SPL 1 : {}
    SPL 2 : {}
    SPL 3 : {}
        
    SPH 1 : {}
    SPH 2 : {}
    SPH 3 : {}
    
    LPL   : {}
    LPH   : {}
                '''.format(self._date,self._spl0,self._spl1,self._spl2,self._sph0,self._sph1,self._sph2,self._lpl,self._lph))
 
        self._sph0 = None
        self._spl0 = None
        self._sph1 = None
        self._spl1 = None
        self._sph2 = None
        self._spl2 = None
        self._sph3 = None
        self._spl3 = None
                 


# In[67]:


for i in BNFSpotData.index.levels[0][0]:
    strategy = DirectionalStrategy(BNFSpotData.loc[i],i)
    strategy.run()


# In[115]:





# In[137]:





# In[143]:


def a():
    a.i = 0
    while (a.i<10):
        b()
def b():
    if(a.i==5):
        print("Hurray")
    a.i+=1
    if(a.i%2 ==0):
        print(i)
    else:
        continue


# In[142]:


a()


# In[ ]:




