import yaml
import random
import argparse
import time as t

class Agent:
    def __init__(self, agent_id, agent_type, cash, sells, buys, reference_prices):
        self.id = agent_id
        self.type = agent_type
        self.cash = cash
        self.initial_sells = dict(sells)
        self.initial_buys = dict(buys)
        self.sells = dict(sells)
        self.buys = dict(buys)
        self.inventory = {prod: qty for prod, qty in self.initial_sells.items()}
        for prod in self.initial_buys:
            self.inventory.setdefault(prod, 0)
        self.reference_prices = reference_prices
        self.sell_prices = {prod: reference_prices.get(prod, 0) for prod in self.initial_sells}
        self.buy_prices  = {prod: reference_prices.get(prod, 0) for prod in self.initial_buys}
        self.known = {}
        self.busy_until = 0

    def is_free(self, current_time):
        return current_time >= self.busy_until

    def can_trade(self, other):
        for prod, qty in self.sells.items():
            if qty > 0 and other.buys.get(prod, 0) > 0:
                price = self.sell_prices.get(prod, 0)
                if other.cash >= price and other.buy_prices.get(prod, 0) >= price:
                    return prod, price
        return None, None

    def buy(self, seller, prod, price):
        seller.inventory[prod] -= 1
        seller.sells[prod] -= 1
        self.cash -= price
        seller.cash += price
        self.inventory[prod] = self.inventory.get(prod, 0) + 1
        print(f"{seller.id} -> {self.id}: buys 1 {prod} at {price}")
        if prod in self.buys:
            self.buys[prod] -= 1
            self.initial_buys[prod] -= 1
            if self.buys[prod] == 0:
                del self.buys[prod]
                del self.initial_buys[prod]
                del self.buy_prices[prod]
        else:
            self.sells[prod] = self.sells.get(prod, 0) + 1
            self.initial_sells[prod] = self.initial_sells.get(prod, 0) + 1
            self.sell_prices[prod] = self.reference_prices.get(prod, price)

    def sell(self, buyer, prod, price):
        self.inventory[prod] -= 1
        self.sells[prod] -= 1
        self.cash += price
        buyer.cash -= price
        buyer.inventory[prod] = buyer.inventory.get(prod, 0) + 1
        print(f"{self.id} -> {buyer.id}: sells 1 {prod} at {price}")
        if prod in buyer.buys:
            buyer.buys[prod] -= 1
            buyer.initial_buys[prod] -= 1
            if buyer.buys[prod] == 0:
                del buyer.buys[prod]
                del buyer.initial_buys[prod]
                del buyer.buy_prices[prod]

    def adjust_prices(self):
        for prod, qty in self.sells.items():
            if qty > 0:
                self.sell_prices[prod] = max(1, int(self.sell_prices[prod] * 0.9))
        for prod, qty in self.buys.items():
            if qty > 0:
                self.buy_prices[prod] = int(self.buy_prices[prod] * 1.1)

class Simulation:
    def __init__(self, config_file):
        with open(config_file) as f:
            cfg = yaml.safe_load(f)
        self.cash = cfg.get('cash', 0)
        self.prices = cfg.get('prices', {})
        self.T = cfg.get('T', 1)
        self.schedule = cfg.get('agents', [])
        self.pending = []
        self.agents = {}
        self.time = 0
        self._prepare_agents()

    def _prepare_agents(self):
        for spec in self.schedule:
            enters = spec.get('enters', 0) * self.T
            for _ in range(spec.get('count', 1)):
                self.pending.append({
                    'type': spec['type'],
                    'enters': enters,
                    'sells': spec.get('sells', {}),
                    'buys': spec.get('buys', {})
                })
        self.pending.sort(key=lambda e: e['enters'])

    def _print_summary(self, label):
        print(f"\n-- State after {label} --")
        for aid in sorted(self.agents):
            ag = self.agents[aid]
            print(f"Agent {aid} - Cash: {ag.cash}")
            print("  Sells:",    ", ".join(f"{p}:{q}" for p,q in ag.sells.items()) or "none")
            print("  Buys:",     ", ".join(f"{p}:{q}" for p,q in ag.buys.items()) or "none")
            print("  Inv-consume:",", ".join(f"{p}:{ag.inventory.get(p,0)}" for p in ag.initial_buys) or "none")
            print("  Inv-resell:", ", ".join(f"{p}:{ag.inventory.get(p,0)}" for p in ag.inventory if p not in ag.initial_buys) or "none")
            print("  Sold:",      ", ".join(f"{p}:{ag.initial_sells.get(p,0)-ag.sells.get(p,0)}" for p in ag.initial_sells) or "none")

    def run(self, finite_steps=None):
        def select_best_partner(agent, free_list):
            cands = [oid for oid in free_list if oid != agent.id]
            known = [oid for oid in cands if oid in agent.known]
            desired = [oid for oid in known if any(agent.known[oid]['sells'].get(p,0) > 0 for p in agent.buys)]
            if desired:
                return random.choice(desired)
            return random.choice(cands) if cands else None

        def select_best_purchase(agent, partner):
            desired = [(prod, partner.sell_prices[prod])
                       for prod,qty in partner.sells.items() if qty>0 and prod in agent.buys and agent.cash>=partner.sell_prices[prod]]
            if desired:
                return min(desired, key=lambda x: x[1])
            opp = []
            for prod,qty in partner.sells.items():
                price = partner.sell_prices.get(prod,0)
                if qty>0 and agent.cash>=price:
                    ref = agent.reference_prices.get(prod, price)
                    margin = ref - price
                    if margin>0:
                        score = margin - price*0.1
                        opp.append((prod, price, score))
            if opp:
                p,pr,_ = max(opp, key=lambda x: x[2])
                return p, pr
            return None, None

        total = finite_steps or 0
        print(f"Running for {total} steps (T={self.T})")
        for step in range(total):
            print(f"\n-- Step {step}, time={self.time} --")
            while self.pending and self.pending[0]['enters'] == step:
                spec = self.pending.pop(0)
                aid = f"{spec['type']}{len(self.agents)+1}"
                ag = Agent(aid, spec['type'], self.cash, spec['sells'], spec['buys'], self.prices)
                self.agents[aid] = ag
                print(f"Agent {aid} entered at step {step}.")

            free = [aid for aid,ag in self.agents.items() if ag.is_free(self.time)]
            random.shuffle(free)
            used = set()
            for aid in free:
                if aid in used: continue
                ag = self.agents[aid]
                available = [oid for oid in free if oid not in used and oid != aid]
                if not available: continue
                pid = select_best_partner(ag, available)
                if pid is None: continue
                partner = self.agents[pid]
                ag.busy_until = partner.busy_until = self.time + self.T
                used.update({aid, pid})

                offer = [p for p in ag.sells if ag.sells[p]>0 and partner.buys.get(p,0)>0]
                want  = [p for p in partner.sells if partner.sells[p]>0 and ag.buys.get(p,0)>0]
                if offer and want:
                    p_self, p_part = offer[0], want[0]
                    ag.inventory[p_self]-=1; ag.sells[p_self]-=1
                    partner.inventory[p_self]+=1; partner.buys[p_self]-=1
                    partner.inventory[p_part]-=1; partner.sells[p_part]-=1
                    ag.inventory[p_part]+=1; ag.buys[p_part]-=1
                    print(f"Troc: {ag.id} gives 1 {p_self} to {partner.id} and receives 1 {p_part}")
                    ag.known[pid]   = {'sells': dict(partner.sells), 'buys': dict(partner.buys)}
                    partner.known[aid] = {'sells': dict(ag.sells),      'buys': dict(ag.buys)}
                    continue

                prod, price = ag.can_trade(partner)
                if prod:
                    ag.sell(partner, prod, price)
                else:
                    prod2, price2 = partner.can_trade(ag)
                    if prod2:
                        partner.sell(ag, prod2, price2)
                    else:
                        po, pr = select_best_purchase(ag, partner)
                        if po:
                            ag.buy(partner, po, pr)
                        else:
                            print(f"{aid} and {pid} interacted but no trade.")

                ag.adjust_prices(); partner.adjust_prices()
                ag.known[pid]   = {'sells': dict(partner.sells), 'buys': dict(partner.buys)}
                partner.known[aid] = {'sells': dict(ag.sells),      'buys': dict(ag.buys)}

            self.time += 1
            self._print_summary(f"step {step}")
            t.sleep(1)
        self._print_summary("end")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file', nargs='?', default='input.yaml')
    parser.add_argument('-s', '--steps', type=int, default=None)
    args = parser.parse_args()
    sim = Simulation(args.config_file)
    sim.run(finite_steps=args.steps)
