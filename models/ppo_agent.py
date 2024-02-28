import pathlib

import torch
from torch import nn
from torch.distributions import Normal

from models.utils import layer_init


class ActorCriticAgent(nn.Module):
    def __init__(self, input_size: int, output_size: int):
        super().__init__()
        self.input_size = input_size
        self.output_size = output_size

        self.critic = nn.Sequential(
            layer_init(nn.Linear(input_size, 64)),
            nn.Tanh(),
            layer_init(nn.Linear(64, 64)),
            nn.Tanh(),
            layer_init(nn.Linear(64, 1), std=1.0),
        )
        self.actor_mean = nn.Sequential(
            layer_init(nn.Linear(input_size, 64)),
            nn.Tanh(),
            layer_init(nn.Linear(64, 64)),
            nn.Tanh(),
            layer_init(nn.Linear(64, output_size), std=0.01),
        )
        self.actor_logstd = nn.Parameter(torch.zeros(1, output_size))


    def get_value(self, x):
        return self.critic(x)

    def get_action_and_value(self, x, action=None):
        action_mean = self.actor_mean(x)
        action_logstd = self.actor_logstd.expand_as(action_mean)
        action_std = torch.exp(action_logstd)
        probs = Normal(action_mean, action_std)

        if action is None:
            action = probs.sample()

        log_probs = probs.log_prob(action).sum(1)
        entropy = probs.entropy().sum(1)
        value = self.critic(x)

        results = {
            "action": action,
            "log_prob": log_probs,
            "entropy": entropy,
            "value": value,
        }

        batch_sz = x.shape[0]
        for k, batch in results.items():
            assert batch.shape[0] == batch_sz, f"wrong {k} shape: {batch.shape}"

        return results

    def save(self, model_path: pathlib.Path) -> None:
        torch.save(self.state_dict(), model_path)

    def load(self, model_path: pathlib.Path):
        pass
