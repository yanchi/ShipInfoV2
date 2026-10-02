<?php

$finder = (new PhpCsFixer\Finder())
    ->in(__DIR__)
    ->exclude('var')
    ->notPath([
        'config/bundles.php',
        'config/reference.php',
    ])
;

return (new PhpCsFixer\Config())
    ->setRules([
        '@Symfony' => true,
        // 代入と配列の => は縦にそろえて書いている（ずれたら自動でそろえ直す）
        'binary_operator_spaces' => [
            'default'   => 'single_space',
            'operators' => [
                '='  => 'align_single_space_minimal',
                '=>' => 'align_single_space_minimal',
            ],
        ],
        // null === $x ではなく $x === null と書いている
        'yoda_style' => false,
        // 文字列の連結は 'a' . $b と書いている
        'concat_space' => ['spacing' => 'one'],
        // 長い配列シェイプの型に合わせて説明がずっと右に寄ってしまうので、そろえない
        'phpdoc_align' => false,
        // 日本語の説明の末尾に「.」を足してしまうので使わない
        'phpdoc_summary' => false,
    ])
    ->setFinder($finder)
;
