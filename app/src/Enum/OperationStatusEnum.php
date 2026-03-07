<?php

namespace App\Enum;

enum OperationStatusEnum: string
{
    case Operating = 'operating';
    case Cancelled = 'cancelled';
    case Delayed   = 'delayed';
    case Suspended = 'suspended';
    case Unknown   = 'unknown';
}
