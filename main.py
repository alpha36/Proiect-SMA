import yaml
import random
import argparse
import time as t

class Agent:
    def __init__(self, agent_id, agent_type, cash, sells, buys):
        self.id = agent_id
        self.type = agent_type
        self.cash = cash
        self.initial_sells = dict(sells)
        self.initial_buys = dict(buys)
        self.sells = dict(sells)
        self.buys = dict(buys)
        self.inventory = {prod: 0 for prod in buys.keys()}
        self.known = set()
        self.busy_until = 0

    def is_free(self, current_time):
        return current_time >= self.busy_until

    def can_trade(self, other, prices):
        for prod, qty in list(self.sells.items()):
            if qty > 0 and other.buys.get(prod, 0) > 0 and other.cash >= prices.get(prod, 0):
                return prod, prices.get(prod, 0)
        return None, None

    def execute_trade(self, other, prod, price):
        self.sells[prod] -= 1
        other.buys[prod] -= 1
        other.cash -= price
        self.cash += price
        other.inventory.setdefault(prod, 0)
        other.inventory[prod] += 1
        print(f"{self.id} to {other.id}: sells 1 {prod} at {price}")

class Simulation:
    def __init__(self, config_file):
        with open(config_file) as f:
            cfg = yaml.safe_load(f)
        self.cash = cfg.get('cash', 0)
        self.prices = cfg.get('prices', {})
        self.T = cfg.get('T', 3)
        self.schedule = cfg.get('agents', [])
        self.pending = []
        self.agents = {}
        self.time = 0
        self._prepare_agents()

    def _prepare_agents(self):
        for spec in self.schedule:
            count = spec.get('count', 1)
            raw_enters = spec.get('enters', 0)
            enters_step = raw_enters * self.T
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
        for aid in sorted(self.agents.keys()):
            ag = self.agents[aid]
            sold = []
            for prod, q0 in ag.initial_sells.items():
                sold_qty = q0 - ag.sells.get(prod, 0)
                if sold_qty > 0:
                    sold.append(f"sells {sold_qty} {prod}")
            remain = []
            for prod, q0 in ag.initial_buys.items():
                bought = ag.inventory.get(prod, 0)
                rem = q0 - bought
                if rem > 0:
                    remain.append(f"buys {rem} {prod}")
            inv = []
            for prod, qty in ag.inventory.items():
                if qty > 0:
                    inv.append(f"has {qty} {prod}")
            parts = [f"{aid} has {ag.cash} cash"] + remain + sold + inv
            print("; ".join(parts))

    def run(self, finite_steps=None):
        if finite_steps:
            total = finite_steps
            print(f"Running for {total} steps (T={self.T})")
        else:
            total = None
            print(f"Running infinite simulation (T scheduling)")
        step = 0
        while True if total is None else step < total:
            print(f"\n-- Step {step}, time={self.time} --")

            while self.pending and self.pending[0]['enters'] == step:
                spec = self.pending.pop(0)
                aid = f"{spec['type']}{len(self.agents)+1}"
                ag = Agent(aid, spec['type'], self.cash, spec['sells'], spec['buys'])
                self.agents[aid] = ag
                print(f"Agent {aid} entered at step {step}.")
            free = [aid for aid, ag in self.agents.items() if ag.is_free(self.time)]
            random.shuffle(free)
            used = set()
            for aid in free:
                if aid in used:
                    continue
                ag = self.agents[aid]
                # alegem candidatii
                candidates = [oid for oid in free if oid not in used and oid != aid]
                if not candidates:
                    continue

                if random.random() < 0.5 and ag.known:
                    known_free = [oid for oid in candidates if oid in ag.known]
                    part_list = known_free or candidates
                else:
                    part_list = [oid for oid in candidates if oid not in ag.known] or candidates
                pid = random.choice(part_list)
                partner = self.agents[pid]
                ag.known.add(pid); partner.known.add(aid)
                # pauze pentru T
                ag.busy_until = partner.busy_until = self.time + self.T
                used.update({aid, pid})
                prod, price = ag.can_trade(partner, self.prices)
                if prod:
                    ag.execute_trade(partner, prod, price)
                else:
                    prod2, price2 = partner.can_trade(ag, self.prices)
                    if prod2:
                        partner.execute_trade(ag, prod2, price2)
                    else:
                        print(f"{aid} and {pid} interacted but no trade.")
            #next time
            self.time += 1
            self._print_summary(f"step {step}")
            step += 1
            t.sleep(1)

        if total:
            self._print_summary("end")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file', nargs='?', default='input.yaml')
    parser.add_argument('-s', '--steps', type=int, default=None)
    args = parser.parse_args()
    sim = Simulation(args.config_file)
    sim.run(finite_steps=args.steps)
