#include "llvm/ADT/TypeSwitch.h"
#include "mlir/IR/BuiltinDialect.h"
#include "rlc/dialect/Operations.hpp"
#include "rlc/dialect/Passes.hpp"
#include "rlc/dialect/conversion/TypeConverter.h"

namespace mlir::rlc
{

#define GEN_PASS_DEF_INSTANTIATETEMPLATESPASS
#include "rlc/dialect/Passes.inc"

	static bool isFullyDeterminedInstantiation(
			mlir::rlc::TemplateInstantiationOp op)
	{
		for (auto type : op.getType().getInputs())
			if (type.isa<mlir::rlc::TemplateParameterType>())
				return false;
		return true;
	}

	struct InstantiateTemplatesPass
			: impl::InstantiateTemplatesPassBase<InstantiateTemplatesPass>
	{
		using impl::InstantiateTemplatesPassBase<
				InstantiateTemplatesPass>::InstantiateTemplatesPassBase;
		llvm::DenseMap<mlir::Type, bool> destructorsCache;

		mlir::Value redirectMaterializedCallFromTraitToExplicitFunction(
				mlir::IRRewriter& rewriter,
				mlir::rlc::ValueTable& symbolTable,
				mlir::rlc::TemplateInstantiationOp op,
				mlir::rlc::TraitDefinition trait)

		{
			mlir::rlc::OverloadResolver resolver(symbolTable);
			rewriter.setInsertionPoint(op);
			size_t index = 0;
			for (auto result : trait.getResults())
				if (result != op.getInputTemplate())
					index++;
				else
					break;

			auto newInstantiation = resolver.instantiateOverload(
					rewriter,
					op.getLoc(),
					trait.getMetaType().getRequestedFunctionNames()[index],
					op.getType().getInputs());

			op.replaceAllUsesWith(newInstantiation);
			op.erase();
			return newInstantiation;
		}

		mlir::Value instantiate(
				mlir::rlc::ModuleBuilder& builder,
				mlir::IRRewriter& rewriter,
				mlir::rlc::ValueTable& symbolTable,
				mlir::rlc::TemplateInstantiationOp op)
		{
			if (isTemplateType(op.getInputTemplate().getType()).failed())
			{
				auto input = op.getInputTemplate();
				op.replaceAllUsesWith(input);
				op.erase();
				return input;
			}
			if (auto trait =
							op.getInputTemplate().getDefiningOp<mlir::rlc::TraitDefinition>())
			{
				auto replacedTraitMethodUsage =
						redirectMaterializedCallFromTraitToExplicitFunction(
								rewriter, symbolTable, op, trait);
				if (auto casted =
								replacedTraitMethodUsage
										.getDefiningOp<mlir::rlc::TemplateInstantiationOp>())
					op = casted;
				else
					return replacedTraitMethodUsage;
			}

			rewriter.setInsertionPoint(op.getInputTemplate().getDefiningOp());
			OverloadResolver resolver(builder.getSymbolTable());
			auto* clone = rewriter.clone(*op.getInputTemplate().getDefiningOp());

			llvm::DenseMap<mlir::rlc::TemplateParameterType, mlir::Type> deductions;
			for (auto [first, second] : llvm::zip(
							 op.getInputTemplate().getType().getInputs(),
							 op.getType().getInputs()))
			{
				resolver.deduceSubstitutions(deductions, first, second).succeeded();
			}
			if (op.getInputTemplate().getType().getNumResults() != 0)
				resolver
						.deduceSubstitutions(
								deductions,
								op.getInputTemplate().getType().getResult(0),
								op.getType().getResult(0))
						.succeeded();

			for (auto sobstitution : deductions)
			{
				mlir::AttrTypeReplacer replacer;
				replacer.addReplacement([&](mlir::Type t) -> std::optional<mlir::Type> {
					if (t == sobstitution.first)
						return sobstitution.second;
					return std::nullopt;
				});
				replacer.recursivelyReplaceElementsIn(clone, true, true, true);
			}

			auto resolvedFunction =
					mlir::cast<mlir::rlc::FunctionOp>(clone).getResult();
			op.replaceAllUsesWith(resolvedFunction);
			op.erase();

			lowerForFields(builder, clone);
			lowerIsOperations(clone, symbolTable);
			lowerAssignOps(builder, clone);
			lowerConstructOps(builder, clone);
			lowerDestructors(destructorsCache, builder, clone);

			return resolvedFunction;
		}

		struct AlreadyReplacedMapEntry
		{
			public:
			mlir::Operation* originalTemplate;
			mlir::Type instationationType;

			bool operator<(const AlreadyReplacedMapEntry& other) const
			{
				return std::pair{ originalTemplate,
													instationationType.getAsOpaquePointer() } <
							 std::pair{ other.originalTemplate,
													other.instationationType.getAsOpaquePointer() };
			}
		};

		void runOnOperation() override
		{
			std::map<AlreadyReplacedMapEntry, mlir::Value> alreadyReplaced;
			mlir::IRRewriter rewriter(&getContext());
			mlir::rlc::ModuleBuilder builder(getOperation());

			bool replacedAtLeastOne = true;
			while (replacedAtLeastOne)
			{
				replacedAtLeastOne = false;
				llvm::SmallVector<mlir::rlc::TemplateInstantiationOp, 4> ops;
				getOperation().walk([&](mlir::rlc::TemplateInstantiationOp op) {
					if (isFullyDeterminedInstantiation(op))
						ops.push_back(op);
				});

				for (auto op : ops)
				{
					AlreadyReplacedMapEntry mapKey{ op.getInputTemplate().getDefiningOp(),
																					op.getType() };
					if (auto iter = alreadyReplaced.find(mapKey);
							iter != alreadyReplaced.end())
					{
						op.replaceAllUsesWith(iter->second);
						op.erase();
					}
					else
					{
						replacedAtLeastOne = true;
						auto newInstance =
								instantiate(builder, rewriter, builder.getSymbolTable(), op);
						alreadyReplaced[mapKey] = newInstance;
					}
				}
			}

			llvm::SmallVector<mlir::rlc::FunctionOp> templates;
			for (auto op : getOperation().getOps<mlir::rlc::FunctionOp>())
			{
				if (isTemplateType(op.getType()).succeeded())
					templates.push_back(op);
			}

			for (auto op : templates)
			{
				op.getOperation()->dropAllUses();
				op.erase();
			}
		}
	};
}	 // namespace mlir::rlc
