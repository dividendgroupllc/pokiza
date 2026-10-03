# Copyright (c) 2026, Sardorbek Qamchibekov and contributors
# For license information, please see license.txt

"""Exchange Rate Revaluation: revaluation jurnali tiyinigacha aniq bo'lishi uchun.

ERPNext har hisob uchun ikki qator yozadi: butun qoldiq yangi kurs bilan kiritiladi va eski kurs bilan
chiqariladi. Eski kurs (kompaniya valyutasidagi qoldiq / hisob valyutasidagi qoldiq) 9 xonaga yaxlitlanadi:
kurs 1 dan kichik bo'lsa (USD kompaniyada so'm hisob: 1 so'm = 0.0000847 $) milliardlab so'mda o'nlab dollar
xato beradi, mayda qoldiqda esa qator 0.00 bo'lib jurnal «Both Debit and Credit values cannot be zero» deb
rad etiladi. Summa so'zda ham 140 belgidan oshib ketishi mumkin.

Bu yerda har hisobga faqat hujjatda hisoblangan foyda/zarar (kompaniya valyutasida, aniq) yoziladi, hisob
valyutasidagi qoldiqqa tegilmaydi. Natija: har hisobning qoldig'i aynan «New Balance In Base Currency» ga
teng bo'ladi, Unrealized hisobiga jami aynan hujjatdagi summa tushadi.

Jurnal turi «Exchange Gain Or Loss» -- ERPNext faqat shu turda kompaniya valyutasidagi summani qayta
hisoblamaydi (o'zining «nol balans» jurnali ham shunday). Hisobotlar (Accounts Receivable, General Ledger)
ikkala turni bir xil ko'radi; teskari jurnal ham ikkala summani almashtiradi.

Yangi qoldiq: kurs 1 dan kichik bo'lsa qoldiq / teskari kurs (yaxlitlanmagan, masalan 11800) bilan hisoblanadi.
Pokiza'da (UZS kompaniya, USD hisoblar) kurs 12100 kabi -- ERPNext'ning o'z hisobi aniq, unga tegilmaydi.
Kursni qo'lda o'zgartirilgan qatorlarga ham tegilmaydi.
"""

import erpnext
import frappe
from erpnext.accounts.doctype.exchange_rate_revaluation.exchange_rate_revaluation import (
	ExchangeRateRevaluation,
)
from erpnext.accounts.utils import get_balance_on
from erpnext.setup.utils import get_exchange_rate
from frappe.model.meta import get_field_precision
from frappe.utils import flt


def exact_new_balance(balance, account_currency, company_currency, posting_date, new_exchange_rate, cache):
	"""balance (hisob valyutasida) / (1 kompaniya valyutasi necha hisob valyutasi).
	None -- ERPNext hisobi qoladi: kompaniya valyutasidagi hisob, kurs 1 dan katta (yaxlitlash xatosi yo'q),
	teskari kurs yo'q yoki qatorda kurs qo'lda o'zgartirilgan."""
	if not account_currency or account_currency == company_currency:
		return None
	if account_currency not in cache:
		cache[account_currency] = (
			get_exchange_rate(account_currency, company_currency, posting_date),
			get_exchange_rate(company_currency, account_currency, posting_date),
		)
	system_rate, quote = cache[account_currency]
	if flt(system_rate) >= 1 or flt(quote) < 1 or flt(new_exchange_rate, 9) != flt(system_rate, 9):
		return None
	return flt(balance) / flt(quote)


class PokizaExchangeRateRevaluation(ExchangeRateRevaluation):
	def validate(self):
		# qo'lda qo'shilgan / o'zgartirilgan qatorlar ham; foyda/zararni ERPNext shundan keyin hisoblaydi
		company_currency = erpnext.get_company_currency(self.company)
		cache = {}
		for d in self.accounts:
			if d.zero_balance:
				continue
			exact = exact_new_balance(
				d.balance_in_account_currency,
				d.account_currency,
				company_currency,
				self.posting_date,
				d.new_exchange_rate,
				cache,
			)
			if exact is not None:
				d.new_balance_in_base_currency = exact
		super().validate()

	@staticmethod
	def calculate_new_account_balance(company, posting_date, account_details):
		"""«Get Entries»: aniq qoldiq bilan (foyda/zarari 0 bo'lgan qatorlar shunga qarab tushib qoladi)."""
		accounts = ExchangeRateRevaluation.calculate_new_account_balance(
			company, posting_date, account_details
		)
		company_currency = erpnext.get_company_currency(company)
		precision = get_field_precision(
			frappe.get_meta("Exchange Rate Revaluation Account").get_field("new_balance_in_base_currency"),
			currency=company_currency,
		)
		cache = {}
		for acc in accounts:
			if acc["zero_balance"]:
				continue
			exact = exact_new_balance(
				acc["balance_in_account_currency"],
				acc["account_currency"],
				company_currency,
				posting_date,
				acc["new_exchange_rate"],
				cache,
			)
			if exact is not None:
				acc["new_balance_in_base_currency"] = exact
				acc["gain_loss"] = flt(exact, precision) - flt(acc["balance_in_base_currency"], precision)
		return accounts

	def make_jv_for_revaluation(self):
		precision = self.precision("gain_loss_unbooked")
		if not flt(self.gain_loss_unbooked, precision):
			return

		accounts = [
			d for d in self.accounts if not d.zero_balance and flt(d.gain_loss, d.precision("gain_loss"))
		]
		if not accounts:
			return

		cost_center = erpnext.get_default_cost_center(self.company)
		journal_entry = frappe.new_doc("Journal Entry")
		journal_entry.voucher_type = "Exchange Gain Or Loss"
		journal_entry.company = self.company
		journal_entry.posting_date = self.posting_date
		journal_entry.multi_currency = 1
		journal_entry.user_remark = f"Exchange Rate Revaluation {self.name}"

		total = 0.0
		for d in accounts:
			gain_loss = flt(d.gain_loss, d.precision("gain_loss"))
			total += gain_loss
			journal_entry.append(
				"accounts",
				{
					"account": d.account,
					"party_type": d.party_type,
					"party": d.party,
					"account_currency": d.account_currency,
					# faqat kompaniya valyutasidagi qoldiq o'zgaradi
					"debit": gain_loss if gain_loss > 0 else 0,
					"credit": -gain_loss if gain_loss < 0 else 0,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": 0,
					"exchange_rate": flt(d.new_exchange_rate, d.precision("new_exchange_rate")),
					"cost_center": cost_center,
					"reference_type": "Exchange Rate Revaluation",
					"reference_name": self.name,
				},
			)

		total = flt(total, precision)
		unrealized_account = self.get_for_unrealized_gain_loss_account()
		journal_entry.append(
			"accounts",
			{
				"account": unrealized_account,
				"balance": get_balance_on(unrealized_account),
				"debit": -total if total < 0 else 0,
				"credit": total if total > 0 else 0,
				"debit_in_account_currency": -total if total < 0 else 0,
				"credit_in_account_currency": total if total > 0 else 0,
				"exchange_rate": 1,
				"cost_center": cost_center,
				"reference_type": "Exchange Rate Revaluation",
				"reference_name": self.name,
			},
		)
		journal_entry.set_total_debit_credit()
		journal_entry.save()
		return journal_entry
