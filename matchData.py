from riotwatcher import LolWatcher, ApiError
import pandas as pd
from time import sleep
from datetime import date
#import json
from tqdm import tqdm

class MatchData:
    def __init__(self, api_key):
        self.lol_watcher = LolWatcher(api_key)
        self.match_df = None
        
    def getList(self, beginTime, patchTime=False, save=True, fileName=None):
        all_matches = []
        ex = ['champion', 'role', 'lane']
        for region, time in servers:
            print(f'{region} started!')
            challenger = self.lol_watcher.league.challenger_by_queue(region,'RANKED_SOLO_5x5')
#            print(f'There are {len(challenger["entries"])} challenger players in {region}.')
            begin_time = (beginTime+time)*1000 if patchTime else beginTime
            for player in tqdm(challenger['entries']):
                sId = player['summonerId']
                player_info = None
                while True:
                    try:
                        player_info = self.lol_watcher.summoner.by_id(region, sId)
                        break
                    except ApiError as err:
                        if err.response.status_code==429:
                            print('Wait 2 minutes...')
                            sleep(120)
                        else:
                            print(f'Something happened with ({region},{sId}): {err.response.status_code}')
                            break
                if not player_info:
                    continue
                t = self.accountList(region, player_info['accountId'], begin_time)
                for d in t:
                    for k in ex:
                        del d[k]
                    d['summoner'] = player_info['name']
                    all_matches.append(d)
            print(f'{region} done! There are {len(all_matches)} matches in total now.')

        self.match_df = pd.DataFrame(all_matches)
        #self.match_df.drop_duplicates(['platformId','gameId'], inplace=True)
        
        if save:
            fileName = fileName or f'match_list_{date.today()}.csv'
            self.match_df.to_csv(fileName, index=False)
            print(f'Match list saved to {fileName}.')

    def accountList(self, regoin, accountId, begin_time):
        lis = []
        i = 0
        attempt = 5
        while attempt>0:
            try:
                m = self.lol_watcher.match.matchlist_by_account(region, accountId, begin_index=i, begin_time=begin_time, queue=[420])
            except ApiError as err:
                if err.response.status_code==429:
                    sleep(120)
                    continue
                elif err.response.status_code==504:
                    sleep(5)
                    attempt -= 1
                    continue
                else:
                    print(err)
                    break
            lis += m['matches']
            i += 100
            if len(m['matches'])<100:
                break
        if attempt==0:
            print('Error')
#        print(f'Add {len(res)} matches for {accountId}.')
        return lis

    def collectData(self, fileName=None, startIndex=0):
        if fileName:
            self.match_df = pd.read_csv(fileName)
        elif self.match_df==None:
            self.match_df = pd.read_csv(f'match_list_{date.today()}.csv')
        
        self.match_df.drop_duplicates(['platformId','gameId'], inplace=True)
        print(f'There are {len(self.match_df)} matches in the list.')
        
        match_region = { region:[] for region in df['platformId'].unique() }
        for i, row in self.match_df.iterrows():
            match_region[row['platformId']].append(row['gameId'])
        
        match_list = []
        while any(match_region.values()):
            for r, l in match_region.items():
                if l:
                    match_list.append((r.lower(),l.pop()))
        match_list = match_list[startIndex:]
        
        data = []
        basic = ['gameId', 'platformId', 'gameCreation', 'gameDuration']
        count = 0
        for r,g in tqdm(match_list):
            match, timeline = self.getData(r,g)
            if not match or not timeline:
                print('I think there is something wrong...')
                print(f'Last match: {count}.')
                break
            d = { key: match[key] for key in basic }
            d['winTeam'] = [team['teamId'] for team in match['teams'] if team['win']=='Win']
            if len(d['winTeam'])!=1:
                print('??')
            else:
                d['winTeam'] = d['winTeam'][0]
            for player in match['participants']:
                d[player['participantId']] = []
                d[player['participantId']+100] = player['teamId']
                d[player['participantId']+500] = player['timeline']['lane']
                d[player['participantId']+600] = player['timeline']['role']
            for frame in timeline['frames']:
                for player in frame['participantFrames'].values():
                    d[player['participantId']] += player['totalGold'],
            for i in range(1,11):
                d[i] = ' '.join(map(str,d[i]))
            data.append(d)
            count += 1
            if count%1000==0 or count==len(match_list):
                with open(rf'match_data_{date.today()}.csv', 'a') as f:
                    df = pd.DataFrame(data)
                    df.to_csv(f, mode='a', header=f.tell()==0, index=False)
                print(f'{count} matches done!')
                data = []
        print(f'ALL DONE! Data saved in match_data_{date.today()}.csv' if data==[] else '???')        
        
    def getData(self, region, match_id, tried=5):
        while tried>0:
            try:
                match = self.lol_watcher.match.by_id(region,match_id)
                timeline = self.lol_watcher.match.timeline_by_match(region,match_id)
                break 
            except ApiError as err:
                if err.response.status_code==429:
#                    print('Wait for 2 minutes...')
                    sleep(120)
                else:
                    sleep(5)
            tried -= 1
        if tried==0:
            print(f'Something went wrong with {region} {match_id}.')
            return None, None
        return match, timeline           
    
    def teamGold(self, fileName=None):
        fileName = fileName or f'match_data_{date.today()}.csv'
        data = list(pd.read_csv(fileName).to_dict('index').values())
        
        maxDuration = max(d['gameDuration'] for d in data)
        maxMinute = maxDuration//60 + 1
        col_B = [f'B{m:02d}' for m in range(maxMinute+1)]
        col_R = [f'R{m:02d}' for m in range(maxMinute+1)]
        
        for d in data:
            for c in col_B+col_R:
                d[c] = 0
            for x in ['101','102','103','104','105', '106','107','108','109','110']:
                del d[x]
            for i in ['1', '2', '3', '4', '5']:
                for minute, gold in enumerate(map(int,d[i].split())):
                    d[col_B[minute]] += gold
                del d[i]
            for i in ['6', '7', '8', '9', '10']:
                for minute, gold in enumerate(map(int,d[i].split())):
                    d[col_R[minute]] += gold
                del d[i]
                
        df = pd.DataFrame(data)
        df.replace(0, np.nan, inplace=True)
        df = df[[col for col in df.columns if col[0] not in ['5', '6']]]
        
        df.to_csv(rf'teamGold_{date.today()}.csv', index=False)
        print(f'Team Gold data saved as teamGold_{date.today()}.csv.')
