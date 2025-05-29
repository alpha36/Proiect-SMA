import yaml
import random
import argparse
import time as t

class Agent:
    def __init__(self, agent_id, agent_type, cash, sells, buys, reference_prices):
        self.id = agent_id
        self.type = agent_type
        self.cash = cash
        # stocuri inițiale
        self.initial_sells = dict(sells)
        self.initial_buys = dict(buys)
        self.sells = dict(sells)
        self.buys = dict(buys)
        # inventar fizic pornește din stocul inițial de vândut și cererile de cumpărare
        self.inventory = dict(self.initial_sells)
        for prod in self.initial_buys:
            self.inventory.setdefault(prod, 0)
        # prețuri de referință și negociere
        self.reference_prices = reference_prices
        self.sell_prices = dict(reference_prices)
        self.buy_prices = dict(reference_prices)
        # istoricul întâlnirilor
        self.known = {}
        self.busy_until = 0

    def is_free(self, current_time):
        return current_time >= self.busy_until

    def can_trade(self, other):
        for prod, qty in self.sells.items():
            if qty > 0 and other.buys.get(prod, 0) > 0:
                price = self.sell_prices.get(prod, 0)
                if other.buy_prices.get(prod, 0) >= price and other.cash >= price:
                    return prod, price
        return None, None

    def can_opportunistic_buy(self, other):
        for prod, qty in other.sells.items():
            if qty > 0 and prod not in self.initial_buys:
                price = other.sell_prices.get(prod, 0)
                if price < self.reference_prices.get(prod, price) and self.cash >= price:
                    return prod, price
        return None, None

    def buy(self, seller, prod, price):
        # cumpărare obișnuită sau oportunistă
        seller.inventory[prod] -= 1
        seller.sells[prod] -= 1
        self.cash -= price
        seller.cash += price
        self.inventory[prod] = self.inventory.get(prod, 0) + 1
        print(f"{seller.id} to {self.id}: buys 1 {prod} at {price}")
        # actualizează dorințe sau ofertă
        if prod in self.buys and self.buys[prod] > 0:
            self.buys[prod] -= 1
            self.initial_buys[prod] -= 1
            if self.buys[prod] == 0:
                del self.buys[prod]
                del self.initial_buys[prod]
        else:
            self.sells[prod] = self.sells.get(prod, 0) + 1
            self.initial_sells[prod] = self.initial_sells.get(prod, 0) + 1
            self.sell_prices[prod] = self.reference_prices.get(prod, price)

    def sell(self, buyer, prod, price):
        # vânzare efectivă
        self.inventory[prod] -= 1
        self.sells[prod] -= 1
        self.cash += price
        buyer.cash -= price
        buyer.inventory[prod] = buyer.inventory.get(prod, 0) + 1
        if prod in buyer.buys and buyer.buys[prod] > 0:
            buyer.buys[prod] -= 1
            buyer.initial_buys[prod] -= 1
            if buyer.buys[prod] == 0:
                del buyer.buys[prod]
                del buyer.initial_buys[prod]
        print(f"{self.id} to {buyer.id}: sells 1 {prod} at {price}")

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
            count = spec.get('count', 1)
            enters_step = spec.get('enters', 0) * self.T
            for _ in range(count):
                self.pending.append({
                    'type': spec['type'],
                    'enters': enters_step,
                    'sells': spec.get('sells', {}),
                    'buys': spec.get('buys', {})
                })
        self.pending.sort(key=lambda e: e['enters'])

    def _print_summary(self, label):
        print(f"\n-- State after {label} --")
        for aid in sorted(self.agents):
            ag = self.agents[aid]
            sells_list = [f"{p}:{q}" for p,q in ag.sells.items()]
            buys_list  = [f"{p}:{q}" for p,q in ag.buys.items()]
            consume_list = [f"{p}:{ag.inventory.get(p,0)}" for p in ag.initial_buys]
            resell_list = [f"{p}:{ag.inventory.get(p,0)}" for p in ag.inventory if p not in ag.initial_buys]
            sold_list = [f"{p}:{ag.initial_sells.get(p,0)-ag.sells.get(p,0)}" for p in ag.initial_sells]

            print(f"Agent {aid} - Cash: {ag.cash}")
            print("  Sells:",    ", ".join(sells_list)    or "none")
            print("  Buys:",     ", ".join(buys_list)     or "none")
            print("  Inventory (consume):", ", ".join(consume_list) or "none")
            print("  Inventory (resell):",  ", ".join(resell_list)  or "none")
            print("  Sold:",     ", ".join(sold_list)      or "none")

    def run(self, finite_steps=None):
        steps = finite_steps or 0
        print(f"Running for {steps} steps (T={self.T})")
        for step in range(steps):
            print(f"\n-- Step {step}, time={self.time} --")
            while self.pending and self.pending[0]['enters'] == step:
                spec = self.pending.pop(0)
                aid = f"{spec['type']}{len(self.agents)+1}"
                ag = Agent(aid, spec['type'], self.cash, spec['sells'], spec['buys'], self.prices)
                self.agents[aid] = ag
                print(f"Agent {aid} entered at step {step}.")

            free = [aid for aid, ag in self.agents.items() if ag.is_free(self.time)]
            random.shuffle(free)
            used = set()
            for aid in free:
                if aid in used: continue
                ag = self.agents[aid]
                candidates = [oid for oid in free if oid not in used and oid != aid]
                if not candidates: continue
                pid = random.choice(candidates)
                partner = self.agents[pid]
                ag.busy_until = partner.busy_until = self.time + self.T
                used.update({aid, pid})

                # Troc: schimb direct de produse dorite
                my_offer = [p for p in ag.sells if ag.sells[p] > 0 and partner.buys.get(p,0) > 0]
                their_offer = [p for p in partner.sells if partner.sells[p] > 0 and ag.buys.get(p,0) > 0]
                if my_offer and their_offer:
                    p_self = my_offer[0]
                    p_part = their_offer[0]
                    # execut schimbul fără cash
                    ag.inventory[p_self] -= 1
                    ag.sells[p_self] -= 1
                    partner.inventory[p_self] = partner.inventory.get(p_self,0) + 1
                    partner.buys[p_self] -= 1

                    partner.inventory[p_part] -= 1
                    partner.sells[p_part] -= 1
                    ag.inventory[p_part] = ag.inventory.get(p_part,0) + 1
                    ag.buys[p_part] -= 1

                    print(f"Troc: {ag.id} gives 1 {p_self} to {partner.id} and receives 1 {p_part}")
                    continue

                traded = False
                prod, price = ag.can_trade(partner)
                if prod:
                    ag.sell(partner, prod, price)
                    traded = True
                else:
                    prod2, price2 = partner.can_trade(ag)
                    if prod2:
                        partner.sell(ag, prod2, price2)
                        traded = True
                    else:
                        opp, pr = ag.can_opportunistic_buy(partner)
                        if opp:
                            ag.buy(partner, opp, pr)
                            traded = True
                        else:
                            print(f"{aid} and {pid} interacted but no trade.")

                if not traded:
                    ag.adjust_prices(); partner.adjust_prices()

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
