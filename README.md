# tradingbot-coinbase-allcoins-abovecertianliquidity
Trading bot on coinbase aerodrome dex who trades all coins above certian liquidity with how much up percent buy stop loss and take profit
how to setup?
you need to create file .env in the same folder where bot is
in .env you need put this
=====
RPC_URL=https://mainnet.base.org
PRIVATE_KEY=HereYourPricateKeyWithoutQuotesPlainAsItIs
=====
RPC_URL should be okay for base chain dont change
equal sign dont put just RPC and PRIV
than start the bot with 
python3 Slippagebot-coinbase.py
notice you need to install python3 just write on google how to install python3 install from official website
than you need to install
python3 install pip3
than run the bot it will give error like missing install
type the error on google it will give solution
basicly you need to install all libraries with
pip3 install request
pip3 install json
etc..
when all libraries are installed it will run without error BUT
you need to get FREE API KEY from here
https://thegraph.com/explorer/subgraphs/GENunSHWLBXm59mBSgPzQ8metBEp9YDfdqwFr91Av1UM?view=Query
than in code where it says 
AERODROME_SUBGRAPH_URL = "https://gateway.thegraph.com/api/547adc7c0f0541cf9e78feaffbc5cce5/subgraphs/id/GENunSHWLBXm59mBSgPzQ8metBEp9YDfdqwFr91Av1UM"
replace text in quotes with https://gateway.thegraph.com/api/{api-key}/subgraphs/id/GENunSHWLBXm59mBSgPzQ8metBEp9YDfdqwFr91Av1UM
replace {api-key} with your api
and you are good to go
notes:
i run this bot for e few weeks outsite of bull run
i am loss 200 euro
what i realized
need to run in bull run
and not to go on all coin pick 1-10 coins and go only with that
!!!!!USE IT AT YOUR OWN RISK I DONT GUARANTUE NOTHING I TOLD YOU THAT I WAS IN LOSS WITH THIS BOT!!!!!!
.
.
and last but not least
Who am I?
Hi, I am Done Gogov blockchain developepr of trading bots.
If you like specific trading have private requirements let me know contact me at donatellorm@gmail.com with subject I LOVE TRADING-BOT and I will get back to you asap
I will develop trading bot as you wish there are no limitations!
HAVE FUN FOLKS!
Thanks for reading if you like this repo give it a star!











