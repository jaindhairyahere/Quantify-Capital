import datetime as dt
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.core.debugger import set_trace


def to_datetime(label):
    return dt.datetime.strptime(label,"%Y-%m-%d %H:%M:%S")
BNFSpotData: pd.DataFrame = pd.read_csv("banknifty5min.csv")
BNFSpotData.datetime = BNFSpotData.datetime.apply(to_datetime)
BNFSpotData["Date"] = BNFSpotData.datetime.apply(lambda x: x.date())
BNFSpotData["Time"] = BNFSpotData.datetime.apply(lambda x: x.time())
BNFSpotData.set_index(["Date","Time"], inplace=True)
BNFSpotData.sort_index(inplace=True)
BNFSpotData = BNFSpotData.drop(["datetime","volume"],axis=1)

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
        
        self._sph = []
        self._spl = []
        self._switch = 0
        
        self._lph = (None,None)
        self._lpl = (None,None)
        
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
        self._square_at_1515 = True
        self._no_trade_after_1500 = True
        
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
        '''.format(self._data.iloc[0].name[0].date(),self._data.iloc[-1].name[0].date(),self._target*100,self._stoploss*100)
    def check_gap(self):
        if(self._curr_date!=self._dataI.name[0]):
            try:
                self._gap_down = (self._data0.name[0].date(),self._data0.open if self._dataI.low > self._data0.open else False)
                self._gap_up = (self._data0.name[0].date(),self._data0.open if self._dataI.high < self._data0.open else False)
            except:
                pass
            if self.position==1:
                o = self.orders[-1]
                pl = (self._dataI.close - o.price)*o.action
                self.orders.append(self.squareOff(pl,'EOD',(self._dataI.name,self._dataI.close)))
            print("\n\n\nDATE CHANGE : {}\n\n\n".format(self._curr_date))
            if self._gap_down and self._gap_down[1]:
                print("GAP DOWN : Open at {}\n\n\n".format(self._data0.open))
                return self._gap_down
            elif self._gap_up and self._gap_up[1]:
                print("GAP UP : Open at {}\n\n\n".format(self._data0.open))
                return self._gap_up
        elif (self._square_at_1515 and self._dataI.name[1]>=dt.time(15,15,0) and self.position==1):
            o = self.orders[-1]
            pl = (self._dataI.close - o.price)*o.action
            self.orders.append(self.squareOff(pl,'EOD',(self._dataI.name,self._dataI.close)))
    
            
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
    def _check_long_short(self,i,new_spl_sph):
        if self.position !=1:      
            # If already (2,3) SPL&SPH found then find LPL and LPH
            if self._buy_level:
                if self._latest == self._lpl:
                    if self._data0.close <= self._buy_level[1]:
                        self.orders.append(self.buy_or_short((self._data0.name,self._data0.close),action=-1))
                elif self._latest == self._lph:
                    if self._data0.close >= self._buy_level[1]: 
                        self.orders.append(self.buy_or_short((self._data0.name,self._data0.close),action=1))
                    
                
                    
        if len(self._sph)>=3 or len(self._spl)>=3:
            # If already found 1 LPL OR LPH then 
            if self._latest:
                if new_spl_sph==-1 and self._latest == self._lpl and self._spl[-1][1]<self._lpl[1]:
                    self._buy_level = self._spl[-1]
                elif new_spl_sph==1 and self._latest == self._lph and self._sph[-1][1]>self._lph[1]:
                    self._buy_level = self._sph[-1]
            self._find_lph(i)
            self._find_lpl(i)
        return i+1
    def _check_square(self):
        '''
            Checks on any time if position is 1 i.e a pending buy/sell trade and checks for SL Breach
            or TGT Aquisition. If there happens to be such case then it makes a square order and returns
                TRUE.
        '''
        if self.position==1:
            for o in self.orders[-1:]:
                pl = (self._data0.close - o.price)*o.action
                if self._data0.close*o.action <= ((1-self._stoploss*o.action)*o.price) *o.action:
                    self.orders.append(self.squareOff(pl,'STOPLOSS'))
                    return True
                elif self._data0.close*o.action >= ((1+self._target*o.action)*o.price)*o.action:
                    self.orders.append(self.squareOff(pl,'TARGET'))
                    return True
        elif self.position==0:
            pass
    def buy_or_short(self, data, action):
        self.position = 1
        o = Order(data[0],data[1],action)
        latest = None
        if action == 1:
            print("BUYING At Price : {} and Time = {} --> BUY LEVEL = {}".format(o.price,o.timestamp,self._buy_level))
            latest = "LPH"
        elif action == -1:
            print("SELLING At Price : {} and Time = {} --> BUY LEVEL = {}".format(o.price,o.timestamp,self._buy_level))
            latest = "LPL"
        def D(some_tuple):
            if some_tuple == (None,None):
                return None
            else:
                return str(some_tuple[0][0].date())
        def T(some_tuple):
            if some_tuple == (None,None):
                return None
            return str(some_tuple[0][1])
                 
        self._log.append([o.timestamp[0].date(),D(self._lpl),T(self._lpl),self._lpl[1],D(self._lph),T(self._lph),self._lph[1]
                ,D(self._spl[-3]),T(self._spl[-3]),self._spl[-3][1],D(self._spl[-2]),T(self._spl[-2]),self._spl[-2][1],D(self._spl[-1]),T(self._spl[-1]),self._spl[-1][1]
                          
                ,D(self._sph[-3]),T(self._sph[-3]),self._sph[-3][1],D(self._sph[-2]),T(self._sph[-2]),self._sph[-2][1],D(self._sph[-1]),T(self._sph[-1]),self._spl[-1][1]
                          ,o.price,o.timestamp[1],o.str_action,
                D(self._buy_level),T(self._buy_level),self._buy_level[1]
                         ])
        #         ,self._latest,self._spl[-1],self._sph[-1]
        #         self._cumPnL.append(self._pnl)
        return o
    def squareOff(self,pl,exit,data=None):
        self._PnL.append(pl)
        self._pnl += pl
        self._cumPnL.append(self._pnl)
        self._trades +=1
                    
        data = data or (self._data0.name,self._data0.close)
        pivot_price = (self._dataI.high+self._dataI.low+self._dataI.close)/3
        r1 = 2*pivot_price - self._dataI.low
        self.position = 0
        stoploss=((1-self._stoploss*self.orders[-1].action)*self.orders[-1].price) *self.orders[-1].action
        o = Order(data[0],data[1],action=0)
        print("SQUARING at Price : {}\nTime : {}".format(data[1],data[0]))
        self._log[-1].append(o.price)
        self._log[-1].append(stoploss)
        self._log[-1].append(exit)
        self._log[-1].append(pl)   
        #         ([o.timestamp[0].date()-dt.timedelta(days=1),o.timestamp[0].date(),pivot_price,r1,
        #                 self._data0.open,self._data0.high,self._data0.low,self._data0.close,o.price,o.timestamp[1],
        #                           o.str_action,self._latest,self._spl[-1],self._sph[-1]])
        return o
    ########################################################################################################
    '''
        Functions for checking LPL- LPH
    '''
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
    #######################################################################################################
    '''
        FUNCTIONS FOR FINDING SPL SPH
    '''
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
    #######################################################################################################
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
    
    ###########################################################################################################
    '''
        Now GAP RULES LONG SHORT FUNCTIONS for trade rules 2 and 3
    '''
    def gap_up_buy(self):
        '''
            Check for position gain opportunity. Execute SHORT order of Trade Rule 2
        '''
        if self.position!=1:
            if self._data0.close<self._buy_level[1]:
                self.orders.append(self.buy_or_short((self._data0.name,self._data0.close),-1))
                return True
        return False
    def gap_down_buy(self):
        '''
            Check for position gain opportunity. Execute LONG order of Trade Rule 3
        '''
        if self.position!=1:
            if self._data0.close>self._buy_level[1]:
                self.orders.append(self.buy_or_short((self._data0.name,self._data0.close),1))
                return True
        return False
    ########################################################################################################
    def run(self):
        i = 2
        print("Begining with data entry : %d\n\n\n\n"%i)
        while(i<len(self._data)):
            ###############################################################################################
            '''
                Set initial driver variables which will be used multiple times in this iteration
            '''
            self._data0 = self._data.iloc[i]
            self._curr_date = self._data.iloc[i].name[0]
            self._dataI = self._data.iloc[i-1]
            self._dataII = self._data.iloc[i-2]
            ################################################################################################
            #Check for day change and gap conditions
            ''' 
                Gap Rules says if there was a gap up/down situation created on the current row. If Yes then
                go 2 rows ahead to directly check for spl/sph
            '''
            gap_rules = self.check_gap()
            # if gap_rules:
            #     i+=2
            #     continue             
            ################################################################################################
            if (len(self.orders)==0 or not(len(self.orders)>0 and self.orders[-1].timestamp[0].date() == self._curr_date)):
                '''If last was made today or then first trade of month has occured.'''
                if self._gap_up and self._gap_up[0]==self._curr_date and self._gap_up[1]!=False:
                    '''
                    If the last gap up recorded was today then check if there was already any buy level set today.
                    If set today then it means that spl is already encountered and so go execute sell order. Finally,
                        also check if today a new spl/sph was identified or any LPH/LPL and then continue for next i
                    
                    If not set today then normally search for any new spl/sph. If spl then set it as buy level.
                    '''

                    if self._lph[1] and self._lph[1] < self._gap_up[1]:
                        if self._buy_level and self._buy_level[0][0].date() == self._curr_date:
                            self.gap_up_buy()
                            new_spl_sph  = self.get_sph_or_sph(i)
                        else:
                            self._switch = 0
                            new_spl_sph  = self.get_sph_or_sph(i)
                            if(new_spl_sph==-1):
                                self._buy_level = self._spl[-1]
                                i+=1
                                continue
                        if len(self._sph)>=3 or len(self._spl)>=3:
                            self._find_lph(i)
                            self._find_lpl(i)   
                        i+=1
                        continue
                elif self._gap_down and self._gap_down[0]==self._curr_date and self._gap_down[1]!=False:
                    '''
                    If the last gap down recorded was today then check if there was already any buy level set today.
                    If set today then it means that sph is already encountered and so go execute buy order. Finally,
                        also check if today a new spl/sph was identified or any LPH/LPL and then continue for next i
                    
                    If not set today then normally search for any new spl/sph. If sph then set it as buy level.
                    '''
                    if self._lpl[1] and self._lpl[1] > self._gap_down[1]:
                        if self._buy_level and self._buy_level[0][0].date() == self._curr_date:
                            self.gap_down_buy()
                        else:
                            new_spl_sph  = self.get_sph_or_sph(i)
                            if(new_spl_sph==1):
                                self._buy_level = self._sph[-1]
                                i+=1
                                continue
                        new_spl_sph  = self.get_sph_or_sph(i)
                        if len(self._sph)>=3 or len(self._spl)>=3:
                            self._find_lph(i)
                            self._find_lpl(i) 
                        i+=1
                        continue        
            
            
            ####################################################################################################
            '''
                Now case remains that if there was no gap up/down today or if there was a gap up/down then first
                    order i.e. a buy/sell is already executed. So now we need to check if we can square and make
                    a trade after checking for spl/sph
                Now irrespective of anything, we check this i for new spl/sph
            '''
            #Find the next SPL SPH
            new_spl_sph  = self.get_sph_or_sph(i)
            #####################################################################################################
            # Sell if Already Bought  
            '''
                If we get to sell now then make i++ and move to next row
            '''
            squared = self._check_square()
            if squared:
                i+=1
                continue
            ####################################################################################################
            '''
                If no trade after 3PM is False or if it is true then row time is <=3PM -> Check for opportunity
                    to create any position
            '''
            if not self._no_trade_after_1500 or (self._no_trade_after_1500 and self._data0.name[1]<=dt.time(15,0,0) ):
                i = self._check_long_short(i,new_spl_sph) 
            else:
                self._find_lph(i)
                self._find_lpl(i)
                i+=1
        #########   PROCESS THE LAST ROW OF DATA ###############
        
        if len(self.orders)>0 and self.orders[-1].str_action != "SQUARE":
            o = self.orders[-1]
            pl = (self._dataI.close - o.price)*o.action
            self.orders.append(self.squareOff(pl,(self._data0.name,self._data0.close),'EOD'))
        #########   CREATE LOG array as a DATAFRAME ############
        self._log = pd.DataFrame(self._log,columns=['Present_Date','LPL Date','LPL Time','LPL Value','LPH Date','LPH Time','LPH Value',
                'SPL1 Date','SPL1 Time','SPL1 - Value','SPL2 Date','SPL2 Time','SPL2 - Value','SPL3 Date','SPL3 Time','SPL3 - Value',
                'SPH1 Date','SPH1 Time','SPH1 - Value','SPH2 Date','SPH2 Time','SPH2 - Value','SPH3 Date','SPL3 Time','SPH3 - Value',
                                                    'BuyingPrice','BuyingTime',
                    'Order Type','BuyLevel Date','BuyLevel Time','BuyingLevel',
                    'SellingPrice','Stoploss','Exit','Individual P&L'])
        #         ,'Latest LPH or LPL','Last SPL','Last SPH'
        self._log['Cumulative P&L'] = pd.Series(self._cumPnL)
        #########   Print Net Profit-Loss and Summary ##########
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
strategy = DirectionalStrategy(BNFSpotData.iloc[(BNFSpotData.index.get_level_values('Date') >= dt.datetime(2019,11,1) ) & (BNFSpotData.index.get_level_values('Date') < dt.datetime(2019,11,30))])
strategy.run()
strategy._log.to_csv('tradelog.csv')