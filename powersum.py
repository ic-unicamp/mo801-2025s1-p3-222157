#
# This file is part of LiteX.
#
# Copyright (c) 2013-2015 Sebastien Bourdeauducq <sb@m-labs.hk>
# Copyright (c) 2019-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.cdc import MultiReg

from litex.gen import *

from litex.soc.interconnect import wishbone
from litex.soc.interconnect.csr import *
from litex.soc.interconnect.csr_eventmanager import *

# Helpers ------------------------------------------------------------------------------------------

def _to_signal(obj):
    return obj.raw_bits() if isinstance(obj, Record) else obj

# Multiplier ----------------------------------------------------------------------------------

class Mult(Module):
    def __init__(self):
        self.a = Signal(64)
        self.b = Signal(64)
        self.r = Signal(64)
        self.comb += self.r.eq(self.a * self.b)

# Power Unit ---------------------------------------------------------------------------------------

class PowerUnit(Module):
    def __init__(self):
        self.base   = Signal(64)
        self.exp    = Signal(3)
        self.result = Signal(64)

        self.submodules.mult1 = mult1 = Mult()
        self.submodules.mult2 = mult2 = Mult()
        self.submodules.mult3 = mult3 = Mult()

        self.comb += [
            mult1.a.eq(self.base),
            mult1.b.eq(self.base),
            mult2.a.eq(mult1.r),
            mult2.b.eq(self.base),
            mult3.a.eq(mult1.r),
            mult3.b.eq(mult1.r)
        ]

        x2 = mult1.r
        x3 = mult2.r
        x4 = mult3.r

        self.comb += [
            If(self.exp == 0,
                self.result.eq(1)
            ).Elif(self.exp == 1,
                self.result.eq(self.base)
            ).Elif(self.exp == 2,
                self.result.eq(x2)
            ).Elif(self.exp == 3,
                self.result.eq(x3)
            ).Elif(self.exp == 4,
                self.result.eq(x4)
            ).Else(
                self.result.eq(0x7FC00000)
            )
        ]

# Power Sum ---------------------------------------------------------------------------------------

class PowerSum(LiteXModule):
    def __init__(self):
        # Entradas CSR
        self.xk_val = CSRStorage(32)
        self.yk_val = CSRStorage(32)
        self.exp    = CSRStorage(3)
        self.enable = CSRStorage(1)  # pulso de escrita
        self.done   = CSRStorage(1)  # fim da transmissão

        # Saídas CSR
        self.result = CSRStatus(64)
        self.valid  = CSRStatus(1)
        self.busy   = CSRStatus(1)

        # Buffers de entrada
        self.x_buf = Array([Signal(32) for _ in range(32)])
        self.y_buf = Array([Signal(32) for _ in range(32)])

        # Estado
        wr_index   = Signal(4)
        wr_bank    = Signal()
        buffer_full = Array([Signal() for _ in range(2)])
        processing  = Array([Signal() for _ in range(2)])
        accum       = Signal(64)
        start_sum   = Signal()

        # Escrita sequencial
        addr = Cat(wr_index, wr_bank)
        self.sync += [
            If(self.enable.re & ~self.busy.status,
                #Display(">>> number received"),
                self.x_buf[addr].eq(self.xk_val.storage),
                self.y_buf[addr].eq(self.yk_val.storage),
                #Display(">>> x = %x", self.xk_val.storage),
                #Display(">>> y = %x", self.yk_val.storage),
                wr_index.eq(wr_index + 1),
                If(wr_index == 15,
                    buffer_full[wr_bank].eq(1),
                    wr_bank.eq(~wr_bank),
                    wr_index.eq(0)
                )
            )
        ]

        # Lógica de início de cálculo
        rd_bank = ~wr_bank
        self.sync += [
            start_sum.eq(0),
            If(buffer_full[rd_bank] & ~processing[rd_bank],
                processing[rd_bank].eq(1),
                buffer_full[rd_bank].eq(0),
                start_sum.eq(1)
            )
        ]

        # Instanciando PowerUnits e Mults
        power_units = [PowerUnit() for _ in range(16)]
        mults = [Mult() for _ in range(16)]
        for i in range(16):
            self.submodules += power_units[i]
            self.submodules += mults[i]

        # Ligando as entradas de potência e multiplicação
        for i in range(16):
            read_addr = Cat(Signal(4, reset=i), rd_bank)
            self.comb += [
                power_units[i].base.eq(self.x_buf[read_addr]),
                power_units[i].exp.eq(self.exp.storage),
                mults[i].a.eq(power_units[i].result),
                mults[i].b.eq(self.y_buf[read_addr])
            ]

        # Soma em árvore
        sum_stage1 = [Signal(64) for _ in range(8)]
        sum_stage2 = [Signal(64) for _ in range(4)]
        sum_stage3 = [Signal(64) for _ in range(2)]
        sum_final  = Signal(64)

        for i in range(8):
            self.comb += sum_stage1[i].eq(mults[2*i].r + mults[2*i+1].r)
        for i in range(4):
            self.comb += sum_stage2[i].eq(sum_stage1[2*i] + sum_stage1[2*i+1])
        for i in range(2):
            self.comb += sum_stage3[i].eq(sum_stage2[2*i] + sum_stage2[2*i+1])
        self.comb += sum_final.eq(sum_stage3[0] + sum_stage3[1])

        donecycle = Signal()
        # Acumulação final e sinalização
        self.sync += [
            If(start_sum,
                #Display(">>> 16 numbers received, read = %x %x %x", self.x_buf[0], self.x_buf[16], wr_bank),
                #Display(">>> Numbers: %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x", self.x_buf[0], self.x_buf[1], self.x_buf[2], self.x_buf[3], self.x_buf[4], self.x_buf[5], self.x_buf[6], self.x_buf[7], self.x_buf[8], self.x_buf[9], self.x_buf[10], self.x_buf[11], self.x_buf[12], self.x_buf[13], self.x_buf[14], self.x_buf[15]),
                #Display(">>> Numbers: %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x", self.x_buf[16], self.x_buf[17], self.x_buf[18], self.x_buf[19], self.x_buf[20], self.x_buf[21], self.x_buf[22], self.x_buf[23], self.x_buf[24], self.x_buf[25], self.x_buf[26], self.x_buf[27], self.x_buf[28], self.x_buf[29], self.x_buf[30], self.x_buf[31]),
                #Display(">>> Mults = %x %x %x %x", power_units[0].base, power_units[0].exp, mults[0].a, mults[0].b),
                #Display(">>> Sum stages = %d %d %d %d %d %d %d %d %d %d %d %d %d %d", sum_stage1[0], sum_stage1[1], sum_stage1[2], sum_stage1[3], sum_stage1[4], sum_stage1[5], sum_stage1[6], sum_stage1[7], sum_stage2[0], sum_stage2[1], sum_stage2[2], sum_stage2[3], sum_stage3[0], sum_stage3[1]),
                #Display(">>> Soma acumulada = %d", accum),
                #Display(">>> Soma estagio = %x", sum_final),
                accum.eq(accum + sum_final),
                *[self.y_buf[Cat(Signal(4, reset=i), ~wr_bank)].eq(0) for i in range(16)],
                processing[~wr_bank].eq(0),
                start_sum.eq(0)
            ).Elif(self.done.re,
                wr_bank.eq(~wr_bank),
                donecycle.eq(1)
            ).Elif(donecycle,
                #Display(">>> DONE received %x", wr_bank),
                #Display(">>> Numbers: %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x", self.y_buf[0], self.y_buf[1], self.y_buf[2], self.y_buf[3], self.x_buf[4], self.x_buf[5], self.x_buf[6], self.x_buf[7], self.x_buf[8], self.x_buf[9], self.x_buf[10], self.x_buf[11], self.x_buf[12], self.x_buf[13], self.x_buf[14], self.x_buf[15]),
                #Display(">>> Numbers: %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x", self.y_buf[16], self.y_buf[17], self.y_buf[18], self.y_buf[19], self.x_buf[20], self.x_buf[21], self.x_buf[22], self.x_buf[23], self.x_buf[24], self.x_buf[25], self.x_buf[26], self.x_buf[27], self.x_buf[28], self.x_buf[29], self.x_buf[30], self.x_buf[31]),
                #Display(">>> Mults = %x %x %x %x", power_units[0].base, power_units[0].exp, mults[0].a, mults[0].b),
                #Display(">>> Sum stages = %x %x %x %x %x %x %x %x %x %x %x %x %x %x", sum_stage1[0], sum_stage1[1], sum_stage1[2], sum_stage1[3], sum_stage1[4], sum_stage1[5], sum_stage1[6], sum_stage1[7], sum_stage2[0], sum_stage2[1], sum_stage2[2], sum_stage2[3], sum_stage3[0], sum_stage3[1]),
                #Display(">>> DONE: Soma acumulada = %d", accum),
                #Display(">>> Soma estagio = %x", sum_final),
                accum.eq(accum + sum_final),
                processing[0].eq(0),
                processing[1].eq(0),
                self.result.status.eq(accum + sum_final),
                *[self.y_buf[Cat(Signal(4, reset=i), ~wr_bank)].eq(0) for i in range(16)],
                wr_index.eq(0),
                self.valid.status.eq(1),
                #Display(">>> VALID = 1"),
                accum.eq(0),
                donecycle.eq(0)
            ).Elif(~self.done.storage,
                self.valid.status.eq(0)
            )
        ]

        # busy = ambos os buffers ocupados
        self.comb += self.busy.status.eq(processing[0] & processing[1])